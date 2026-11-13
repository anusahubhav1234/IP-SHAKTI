"""In-memory BM25 index per user, rebuilt only when that user's chunks change.

Why not Postgres full-text search: it has no Telugu/Hindi configuration. Why per user: IDF statistics
should reflect the corpus the user can actually search, and it keeps ownership isolation trivial."""
import math
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.rag.tokenizer import tokenize
from app.rag.types import Hit

class BM25Lucene(BM25Okapi):
    """BM25 with the Lucene/Elasticsearch IDF, log(1 + (N - n + 0.5) / (n + 0.5)), which is always > 0.

    rank_bm25's default IDF is <= 0 for any term present in half or more of the chunks, and its fallback
    floor can itself be <= 0 on small corpora. That made keyword search return nothing for a user's first
    few documents (found by tests), so the IDF is overridden. Scoring is otherwise standard Okapi BM25."""

    def _calc_idf(self, nd):
        for word, freq in nd.items():
            self.idf[word] = math.log(1.0 + (self.corpus_size - freq + 0.5) / (freq + 0.5))
        self.average_idf = sum(self.idf.values()) / len(self.idf) if self.idf else 0.0


MAX_CACHED_USERS = 32
_lock = threading.Lock()
_cache: OrderedDict[uuid.UUID, "_Index"] = OrderedDict()


@dataclass
class _Index:
    fingerprint: tuple
    bm25: BM25Okapi | None
    hits: list[Hit]  # parallel to the BM25 corpus; carries text + citation metadata


def _fingerprint(db: Session, user_id: uuid.UUID) -> tuple:
    row = db.execute(
        select(func.count(DocumentChunk.id), func.max(DocumentChunk.created_at), func.min(DocumentChunk.created_at))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.owner_id == user_id, Document.status == "ready")).one()
    return tuple(row)


def _build(db: Session, user_id: uuid.UUID, fingerprint: tuple) -> _Index:
    rows = db.execute(
        select(DocumentChunk, Document.title)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.owner_id == user_id, Document.status == "ready")
        .order_by(Document.id, DocumentChunk.chunk_index)).all()
    hits = [Hit(chunk_id=c.id, document_id=c.document_id, document_title=t, page_number=c.page_number,
                section_heading=c.section_heading, text=c.text, language=c.language) for c, t in rows]
    # Heading is indexed too: "ATTENDANCE" in a heading should help match attendance questions.
    # A chunk with no tokens gets a placeholder that can never match a query (it is not a \w character).
    corpus = [tokenize(f"{h.section_heading or ''} {h.text}") or ["\u2205"] for h in hits]
    bm25 = BM25Lucene(corpus) if corpus else None
    return _Index(fingerprint, bm25, hits)


def get_index(db: Session, user_id: uuid.UUID) -> _Index:
    fp = _fingerprint(db, user_id)
    with _lock:
        idx = _cache.get(user_id)
        if idx is not None and idx.fingerprint == fp:
            _cache.move_to_end(user_id)
            return idx
        idx = _build(db, user_id, fp)
        _cache[user_id] = idx
        _cache.move_to_end(user_id)
        while len(_cache) > MAX_CACHED_USERS:
            _cache.popitem(last=False)
        return idx


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def bm25_search(db: Session, user_id: uuid.UUID, query: str, k: int,
                doc_ids: list[uuid.UUID] | None = None) -> list[Hit]:
    idx = get_index(db, user_id)
    q = tokenize(query)
    if idx.bm25 is None or not q:
        return []
    scores = idx.bm25.get_scores(q)
    allowed = set(doc_ids) if doc_ids else None
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    out: list[Hit] = []
    for i in order:
        if scores[i] <= 0:
            break
        h = idx.hits[i]
        if allowed is not None and h.document_id not in allowed:
            continue
        # copy so cached hits are never mutated by fusion
        out.append(Hit(h.chunk_id, h.document_id, h.document_title, h.page_number, h.section_heading, h.text,
                       h.language, score=float(scores[i]), bm25_rank=len(out) + 1, bm25_score=float(scores[i])))
        if len(out) >= k:
            break
    return out
