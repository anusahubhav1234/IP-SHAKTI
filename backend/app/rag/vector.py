import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.rag.types import Hit


def _query(user_id, qvec, k, doc_ids):
    dist = DocumentChunk.embedding.cosine_distance(qvec).label("dist")
    stmt = (select(DocumentChunk, Document.title, dist)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.owner_id == user_id, Document.status == "ready",
                   DocumentChunk.embedding.is_not(None)))
    if doc_ids:
        stmt = stmt.where(Document.id.in_(doc_ids))
    return stmt.order_by(dist).limit(k)


def _to_hits(rows) -> list[Hit]:
    hits = []
    for rank, (c, title, dist) in enumerate(rows, start=1):
        sim = 1.0 - float(dist)  # cosine similarity
        hits.append(Hit(chunk_id=c.id, document_id=c.document_id, document_title=title,
                        page_number=c.page_number, section_heading=c.section_heading, text=c.text,
                        language=c.language, score=sim, vector_rank=rank, vector_score=sim))
    return hits


def vector_search(db: Session, user_id: uuid.UUID, qvec: list[float], k: int,
                  doc_ids: list[uuid.UUID] | None = None) -> list[Hit]:
    """Cosine-similarity search over the user's ready documents only (ownership enforced in SQL).

    HNSW applies the WHERE filter *after* the index scan, so with many users' chunks in one table a
    selective filter can return fewer than k rows. We raise ef_search, and if the result is still short
    while enough matching chunks exist, fall back to an exact scan so recall never silently drops."""
    db.execute(text("SET LOCAL hnsw.ef_search = 200"))
    rows = db.execute(_query(user_id, qvec, k, doc_ids)).all()
    if len(rows) < k:
        available = db.scalar(
            select(func.count()).select_from(DocumentChunk).join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.owner_id == user_id, Document.status == "ready", DocumentChunk.embedding.is_not(None),
                   *( [Document.id.in_(doc_ids)] if doc_ids else [] )))
        if available > len(rows):
            db.execute(text("SET LOCAL enable_indexscan = off"))
            rows = db.execute(_query(user_id, qvec, k, doc_ids)).all()
            db.execute(text("SET LOCAL enable_indexscan = on"))
    return _to_hits(rows)
