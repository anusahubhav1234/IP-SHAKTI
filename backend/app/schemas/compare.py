import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.chat import CitationOut, Language

DEFAULT_ASPECTS = ["Eligibility criteria", "Important dates and deadlines", "Fees",
                   "Rules and regulations", "Requirements and required documents"]


class CompareRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=2, max_length=5)
    aspects: list[str] | None = Field(default=None, min_length=1, max_length=6)
    language: Language | None = None


class CompareDoc(BaseModel):
    label: str
    document_id: uuid.UUID
    title: str


class CompareCell(BaseModel):
    document_id: uuid.UUID
    found: bool
    value: str
    verified: bool
    citation: CitationOut | None = None


class CompareRow(BaseModel):
    aspect: str
    cells: list[CompareCell]


class CompareClaim(BaseModel):
    text: str
    verified: bool
    citations: list[CitationOut]


class CompareResponse(BaseModel):
    status: Literal["ok", "insufficient_evidence"]
    language: str
    documents: list[CompareDoc]
    rows: list[CompareRow]
    similarities: list[CompareClaim]
    differences: list[CompareClaim]
    latency_ms: int
