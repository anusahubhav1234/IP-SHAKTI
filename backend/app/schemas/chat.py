import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["en", "hi", "te"]
Status = Literal["answered", "insufficient_evidence", "unverified_withheld"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: uuid.UUID | None = None
    language: Language | None = None            # response language; None = same as the question
    mode: Literal["vector", "bm25", "hybrid", "hybrid_rerank"] = "hybrid"
    top_k: int | None = Field(default=None, ge=1, le=10)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int | None = None
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    document_title: str
    page_number: int | None
    section_heading: str | None = None
    excerpt: str
    verified: bool
    retrieval_score: float | None
    open_url: str | None = None   # relative API path; PDFs open at the cited page via #page=N


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    status: Status
    insufficient_evidence: bool
    language: str
    detected_language: str
    retrieval_mode: str
    rewritten_query: str | None = None
    citations: list[CitationOut]
    latency_ms: int
    timings_ms: dict[str, float]


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    detected_language: str | None
    response_language: str | None
    insufficient_evidence: bool
    latency_ms: int | None
    created_at: datetime
    my_feedback: int | None = None
    citations: list[CitationOut] = []


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationOut]
    total: int


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class FeedbackIn(BaseModel):
    rating: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackOut(BaseModel):
    message_id: uuid.UUID
    rating: int
    comment: str | None
