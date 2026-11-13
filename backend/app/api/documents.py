import uuid
from pathlib import Path

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request,
                     UploadFile, status)
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.limiter import limiter
from app.database.session import get_db
from app.models import Document, DocumentCategory, DocumentChunk, ProcessingJob, User
from app.schemas.documents import (CategoryCreate, CategoryOut, ChunkList, ChunkOut, DocumentList,
                                   DocumentOut, DocumentStatus)
from app.services import files as fs
from app.services.audit import log_action
from app.services.processing import process_document

router = APIRouter(prefix="/api", tags=["documents"])


# ---- access helpers -------------------------------------------------------------------------

def get_accessible_document(db: Session, user: User, doc_id: uuid.UUID) -> Document:
    """Owner or admin only. Returns 404 (not 403) for other users' documents so existence is not leaked."""
    doc = db.get(Document, doc_id)
    if doc is None or (doc.owner_id != user.id and user.role != "admin"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


def _chunk_counts(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = db.execute(select(DocumentChunk.document_id, func.count()).where(DocumentChunk.document_id.in_(ids))
                      .group_by(DocumentChunk.document_id)).all()
    return {d: c for d, c in rows}


def _to_out(doc: Document, counts: dict) -> DocumentOut:
    out = DocumentOut.model_validate(doc)
    out.chunk_count = counts.get(doc.id, 0)
    return out


# ---- documents ------------------------------------------------------------------------------

@router.post("/documents/upload", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("30/minute")
async def upload_document(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=255),
    category_id: uuid.UUID | None = Form(default=None),
    as_faq: bool = Form(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filename = fs.safe_filename(file.filename)
    source_type = fs.detect_source_type(filename)
    if as_faq:
        if source_type != "csv":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "as_faq is only valid for CSV files.")
        source_type = "faq"
    data = await fs.read_limited(file)
    fs.validate_content(data, "csv" if source_type == "faq" else source_type)

    if category_id is not None:
        cat = db.get(DocumentCategory, category_id)
        if cat is None or cat.owner_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    digest = fs.sha256_hex(data)
    existing = db.scalar(select(Document).where(Document.owner_id == user.id, Document.sha256 == digest))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This file was already uploaded (document {existing.id}).")

    path = fs.store_file(user.id, "csv" if source_type == "faq" else source_type, data)
    doc = Document(owner_id=user.id, category_id=category_id,
                   title=(title or Path(filename).stem).strip()[:255] or "Untitled",
                   filename=filename, source_type=source_type, mime_type=fs.MIME["csv" if source_type == "faq" else source_type],
                   size_bytes=len(data), sha256=digest, storage_path=path, status="pending")
    db.add(doc)
    try:
        db.flush()
        job = ProcessingJob(document_id=doc.id, status="queued")
        db.add(job)
        log_action(db, action="document.upload", user_id=user.id, entity_type="document",
                   entity_id=str(doc.id), request=request, details={"filename": filename, "size": len(data)})
        db.commit()
    except Exception:
        db.rollback()
        fs.delete_file(path)
        raise
    background.add_task(process_document, doc.id, job.id)
    return _to_out(doc, {})


@router.get("/documents", response_model=DocumentList)
def list_documents(
    q: str | None = Query(default=None, max_length=100),
    status_: str | None = Query(default=None, alias="status"),
    category_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Document).where(Document.owner_id == user.id)
    if q:
        like = f"%{q.replace('%', r'\%').replace('_', r'\_')}%"
        stmt = stmt.where(or_(Document.title.ilike(like), Document.filename.ilike(like)))
    if status_:
        if status_ not in ("pending", "processing", "ready", "failed"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid status filter")
        stmt = stmt.where(Document.status == status_)
    if category_id:
        stmt = stmt.where(Document.category_id == category_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    docs = db.scalars(stmt.order_by(Document.uploaded_at.desc()).limit(limit).offset(offset)).all()
    counts = _chunk_counts(db, [d.id for d in docs])
    return DocumentList(items=[_to_out(d, counts) for d in docs], total=total)


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = get_accessible_document(db, user, doc_id)
    return _to_out(doc, _chunk_counts(db, [doc.id]))


@router.get("/documents/{doc_id}/status", response_model=DocumentStatus)
def get_status(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = get_accessible_document(db, user, doc_id)
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.document_id == doc.id)
                    .order_by(ProcessingJob.created_at.desc()).limit(1))
    return DocumentStatus(document_id=doc.id, status=doc.status, stage=job.stage if job else None,
                          error=job.error if job else None, started_at=job.started_at if job else None,
                          finished_at=job.finished_at if job else None,
                          chunk_count=_chunk_counts(db, [doc.id]).get(doc.id, 0))


@router.get("/documents/{doc_id}/chunks", response_model=ChunkList)
def get_chunks(doc_id: uuid.UUID, page: int | None = Query(default=None, ge=1),
               limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = get_accessible_document(db, user, doc_id)
    stmt = select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
    if page is not None:
        stmt = stmt.where(DocumentChunk.page_number == page)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(DocumentChunk.chunk_index).limit(limit).offset(offset)).all()
    return ChunkList(items=[ChunkOut.model_validate(c) for c in items], total=total)


@router.get("/documents/{doc_id}/file")
def download_file(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = get_accessible_document(db, user, doc_id)
    if not Path(doc.storage_path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File is no longer available")
    disposition = "inline" if doc.source_type == "pdf" else "attachment"
    return FileResponse(doc.storage_path, media_type=doc.mime_type, filename=doc.filename,
                        content_disposition_type=disposition,
                        headers={"X-Content-Type-Options": "nosniff"})


@router.post("/documents/{doc_id}/reprocess", response_model=DocumentStatus, status_code=status.HTTP_202_ACCEPTED)
def reprocess(doc_id: uuid.UUID, background: BackgroundTasks, request: Request,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = get_accessible_document(db, user, doc_id)
    if doc.status == "processing":
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is already being processed")
    job = ProcessingJob(document_id=doc.id, status="queued")
    doc.status = "pending"
    db.add(job)
    log_action(db, action="document.reprocess", user_id=user.id, entity_type="document",
               entity_id=str(doc.id), request=request)
    db.commit()
    background.add_task(process_document, doc.id, job.id)
    return DocumentStatus(document_id=doc.id, status="pending", stage=None, error=None, started_at=None,
                          finished_at=None, chunk_count=0)


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: uuid.UUID, request: Request, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    doc = get_accessible_document(db, user, doc_id)
    path = doc.storage_path
    log_action(db, action="document.delete", user_id=user.id, entity_type="document",
               entity_id=str(doc.id), request=request, details={"filename": doc.filename})
    db.delete(doc)  # chunks + jobs cascade in the database
    db.commit()
    fs.delete_file(path)


# ---- categories -----------------------------------------------------------------------------

@router.get("/categories", response_model=list[CategoryOut])
def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(DocumentCategory).where(DocumentCategory.owner_id == user.id)
                      .order_by(DocumentCategory.name)).all()


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Name cannot be blank")
    if db.scalar(select(DocumentCategory.id).where(DocumentCategory.owner_id == user.id,
                                                   func.lower(DocumentCategory.name) == name.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Category already exists")
    cat = DocumentCategory(owner_id=user.id, name=name)
    db.add(cat)
    db.commit()
    return cat


@router.delete("/categories/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(cat_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cat = db.get(DocumentCategory, cat_id)
    if cat is None or cat.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    db.delete(cat)
    db.commit()
