import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.rag import embeddings
from app.rag.bm25 import bm25_search
from app.core.config import get_settings
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.reranker import get_reranker
from app.rag.types import Hit
from app.rag.vector import vector_search

MODES = ("vector", "bm25", "hybrid", "hybrid_rerank")
CANDIDATE_MULTIPLIER = 4   # each retriever fetches max(20, 4*top_k) candidates before fusion
MIN_CANDIDATES = 20


@dataclass
class RetrievalResult:
    hits: list[Hit]
    mode: str
    timings_ms: dict[str, float] = field(default_factory=dict)


def retrieve(db: Session, user_id: uuid.UUID, query: str, mode: str = "hybrid", top_k: int = 5,
             doc_ids: list[uuid.UUID] | None = None) -> RetrievalResult:
    """Single entry point used by the search API, the RAG chat pipeline and the evaluation harness, so all
    three measure the same code. 'vector' is the baseline for the hybrid-vs-baseline comparison."""
    if mode not in MODES:
        raise ValueError(f"Unknown retrieval mode: {mode}")
    n = max(MIN_CANDIDATES, top_k * CANDIDATE_MULTIPLIER)
    timings: dict[str, float] = {}

    def timed(name, fn):
        t = time.perf_counter()
        out = fn()
        timings[name] = round((time.perf_counter() - t) * 1000, 1)
        return out

    vec_hits: list[Hit] = []
    kw_hits: list[Hit] = []
    if mode in ("vector", "hybrid", "hybrid_rerank"):
        qvec = timed("embed_query", lambda: embeddings.get_embedder().embed_query(query))
        vec_hits = timed("vector_search", lambda: vector_search(db, user_id, qvec, n, doc_ids))
    if mode in ("bm25", "hybrid", "hybrid_rerank"):
        kw_hits = timed("bm25_search", lambda: bm25_search(db, user_id, query, n, doc_ids))

    if mode == "vector":
        hits = vec_hits[:top_k]
    elif mode == "bm25":
        hits = kw_hits[:top_k]
    elif mode == "hybrid":
        hits = timed("fusion", lambda: reciprocal_rank_fusion([vec_hits, kw_hits]))[:top_k]
    else:  # hybrid_rerank: fuse, take the best candidates, let the cross-encoder reorder them
        fused = timed("fusion", lambda: reciprocal_rank_fusion([vec_hits, kw_hits]))[:max(top_k, get_settings().rerank_candidates)]
        hits = timed("rerank", lambda: _rerank(query, fused))[:top_k]
    return RetrievalResult(hits=hits, mode=mode, timings_ms=timings)


def _rerank(query: str, candidates: list[Hit]) -> list[Hit]:
    if not candidates:
        return []
    scores = get_reranker().score(query, [h.text for h in candidates])
    for h, sc in zip(candidates, scores):
        h.rerank_score = float(sc)
        h.score = float(sc)
    return sorted(candidates, key=lambda h: (-h.rerank_score, str(h.chunk_id)))
