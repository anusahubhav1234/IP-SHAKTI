import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config import get_settings
from app.database.session import get_db
from app.models import AuditLog, Conversation, Document, DocumentChunk, User
from app.schemas.admin import (AdminDocumentList, AdminDocumentOut, AdminUserList, AdminUserOut, AdminUserUpdate)
from app.services import stats
from app.services.audit import log_action

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _like(q: str) -> str:
    return f"%{q.replace('%', r'\%').replace('_', r'\_')}%"


@router.get("/overview")
def admin_overview(db: Session = Depends(get_db)):
    return {**stats.overview(db, None), **stats.global_extras(db)}


@router.get("/users", response_model=AdminUserList)
def list_users(q: str | None = Query(default=None, max_length=100), limit: int = Query(default=25, ge=1, le=100),
               offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    base = select(User)
    if q:
        base = base.where(or_(User.email.ilike(_like(q)), User.full_name.ilike(_like(q))))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    users = db.scalars(base.order_by(User.created_at.desc()).limit(limit).offset(offset)).all()
    ids = [u.id for u in users]
    docs = dict(db.execute(select(Document.owner_id, func.count()).where(Document.owner_id.in_(ids)).group_by(Document.owner_id)).all())
    convs = dict(db.execute(select(Conversation.user_id, func.count()).where(Conversation.user_id.in_(ids)).group_by(Conversation.user_id)).all())
    return AdminUserList(total=total, items=[AdminUserOut(
        id=u.id, email=u.email, full_name=u.full_name, role=u.role, is_active=u.is_active, created_at=u.created_at,
        last_login_at=u.last_login_at, document_count=docs.get(u.id, 0), conversation_count=convs.get(u.id, 0)) for u in users])


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(user_id: uuid.UUID, body: AdminUserUpdate, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.id == admin.id:  # prevents locking yourself (and possibly everyone) out
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own role or status")
    changes = {}
    if body.is_active is not None and body.is_active != target.is_active:
        target.is_active, changes["is_active"] = body.is_active, body.is_active
    if body.role is not None and body.role != target.role:
        target.role, changes["role"] = body.role, body.role
    log_action(db, action="admin.user_update", user_id=admin.id, entity_type="user", entity_id=str(target.id),
               request=request, details=changes)
    db.commit()
    docs = db.scalar(select(func.count()).select_from(Document).where(Document.owner_id == target.id))
    convs = db.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id == target.id))
    return AdminUserOut(id=target.id, email=target.email, full_name=target.full_name, role=target.role,
                        is_active=target.is_active, created_at=target.created_at, last_login_at=target.last_login_at,
                        document_count=docs, conversation_count=convs)


@router.get("/documents", response_model=AdminDocumentList)
def list_all_documents(q: str | None = Query(default=None, max_length=100), status_: str | None = Query(default=None, alias="status"),
                       limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
                       db: Session = Depends(get_db)):
    """All documents of all users. Deleting one: DELETE /api/documents/{id} (admins are allowed)."""
    base = select(Document, User.email).join(User, User.id == Document.owner_id)
    if q:
        base = base.where(or_(Document.title.ilike(_like(q)), Document.filename.ilike(_like(q)), User.email.ilike(_like(q))))
    if status_:
        if status_ not in ("pending", "processing", "ready", "failed"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid status filter")
        base = base.where(Document.status == status_)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(base.order_by(Document.uploaded_at.desc()).limit(limit).offset(offset)).all()
    counts = dict(db.execute(select(DocumentChunk.document_id, func.count())
                             .where(DocumentChunk.document_id.in_([d.id for d, _ in rows])).group_by(DocumentChunk.document_id)).all())
    return AdminDocumentList(total=total, items=[AdminDocumentOut(
        id=d.id, title=d.title, filename=d.filename, owner_email=email, source_type=d.source_type, status=d.status,
        size_bytes=d.size_bytes, chunk_count=counts.get(d.id, 0), uploaded_at=d.uploaded_at) for d, email in rows])


@router.get("/system-health")
def system_health(db: Session = Depends(get_db)):
    s = get_settings()
    checks: dict[str, dict] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
        checks["pgvector"] = {"ok": db.scalar(text("SELECT count(*) FROM pg_extension WHERE extname='vector'")) == 1}
    except Exception:
        checks["database"] = {"ok": False}
    storage = Path(s.storage_dir)
    try:
        storage.mkdir(parents=True, exist_ok=True)
        probe = storage / ".healthcheck"
        probe.write_text("ok")
        probe.unlink()
        du = shutil.disk_usage(storage)
        checks["storage"] = {"ok": True, "free_mb": du.free // 2**20}
    except OSError:
        checks["storage"] = {"ok": False}
    # configuration presence only: secrets are never returned
    checks["llm"] = {"ok": bool(s.gemini_api_key and s.gemini_api_key.get_secret_value().strip()), "model": s.gemini_model}
    checks["embeddings"] = {"ok": True, "provider": s.embedding_provider, "model": s.embedding_model, "dim": s.embedding_dim}
    checks["reranker"] = {"ok": None, "model": s.reranker_model, "note": "loaded lazily on first hybrid_rerank request"}
    ocr = {"ok": False, "languages": []}
    if shutil.which("tesseract"):
        try:
            import pytesseract
            langs = [l for l in pytesseract.get_languages() if l in ("eng", "hin", "tel")]
            ocr = {"ok": s.ocr_enabled and bool(langs), "languages": langs}
        except Exception:
            pass
    checks["ocr"] = ocr
    ok = all(c["ok"] for k, c in checks.items() if k in ("database", "pgvector", "storage"))
    pending_embed = db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.embedding.is_(None))) or 0
    errors_24h = db.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.action.in_(("chat_error", "compare_error")), AuditLog.created_at >= func.now() - text("interval '24 hours'"))) or 0
    return {"status": "healthy" if ok else "degraded", "environment": s.environment, "checks": checks,
            "chunks_without_embedding": pending_embed, "llm_errors_last_24h": errors_24h}
