import uuid
from dataclasses import dataclass


@dataclass
class Hit:
    """One retrieved passage with everything a citation needs. Scores from each retriever are kept
    so evaluation can show exactly where a result came from."""
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page_number: int | None
    section_heading: str | None
    text: str
    language: str | None
    score: float = 0.0           # final score for the chosen mode (cosine sim / BM25 / RRF)
    vector_rank: int | None = None
    vector_score: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None
