import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Mode = Literal["vector", "bm25", "hybrid", "hybrid_rerank"]


class GoldRef(BaseModel):
    document_id: uuid.UUID
    page: int | None = Field(default=None, ge=1)   # None = any page of that document


class BenchmarkItem(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    language: Literal["en", "hi", "te"] = "en"
    relevant: list[GoldRef] = Field(default_factory=list, max_length=20)  # empty = unanswerable (not scored)


class BenchmarkCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    items: list[BenchmarkItem] = Field(min_length=1, max_length=200)


class BenchmarkOut(BaseModel):
    id: uuid.UUID
    name: str
    n_items: int
    n_scored: int
    created_at: datetime


class BenchmarkDetail(BenchmarkOut):
    items: list[BenchmarkItem]


class RunCreate(BaseModel):
    benchmark_id: uuid.UUID
    modes: list[Mode] = Field(default=["vector", "hybrid", "hybrid_rerank"], min_length=1, max_length=4)
    top_k: int = Field(default=5, ge=1, le=10)


class RunOut(BaseModel):
    id: uuid.UUID
    benchmark_id: uuid.UUID
    benchmark_name: str | None = None
    top_k: int
    created_at: datetime
    results: dict[str, Any]
