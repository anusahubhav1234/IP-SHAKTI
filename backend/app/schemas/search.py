import uuid
from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["vector", "bm25", "hybrid", "hybrid_rerank"]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: Mode = "vector"
    top_k: int = Field(default=5, ge=1, le=20)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)


class HybridSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page_number: int | None
    section_heading: str | None
    language: str | None
    text: str
    score: float
    vector_rank: int | None = None
    vector_score: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None


class SearchResponse(BaseModel):
    query: str
    detected_language: str
    mode: str
    top_k: int
    results: list[SearchHit]
    timings_ms: dict[str, float]
