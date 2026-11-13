import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocStatus = Literal["pending", "processing", "ready", "failed"]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    filename: str
    source_type: str
    size_bytes: int
    language: str | None
    doc_date: date | None
    page_count: int | None
    status: DocStatus
    category_id: uuid.UUID | None
    uploaded_at: datetime
    chunk_count: int = 0


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int


class DocumentStatus(BaseModel):
    document_id: uuid.UUID
    status: DocStatus
    stage: str | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    chunk_count: int


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    page_number: int | None
    section_heading: str | None
    language: str | None
    text: str


class ChunkList(BaseModel):
    items: list[ChunkOut]
    total: int


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
