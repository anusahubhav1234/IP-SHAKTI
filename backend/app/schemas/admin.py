import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    document_count: int
    conversation_count: int


class AdminUserList(BaseModel):
    items: list[AdminUserOut]
    total: int


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: Literal["user", "admin"] | None = None


class AdminDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    filename: str
    owner_email: str
    source_type: str
    status: str
    size_bytes: int
    chunk_count: int
    uploaded_at: datetime


class AdminDocumentList(BaseModel):
    items: list[AdminDocumentOut]
    total: int
