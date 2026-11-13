"""Real aggregates computed from the database. Nothing here is estimated or pre-filled: a user with no
activity gets zeros."""
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import (AuditLog, Conversation, Document, DocumentChunk, EvaluationRun, Message, ProcessingJob,
                        User, UserFeedback)

DAYS = 14


def _daily(db: Session, actions: tuple[str, ...], user_id: uuid.UUID | None) -> list[dict]:
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=DAYS - 1)
    day = func.date(AuditLog.created_at)
    q = select(day, AuditLog.action, func.count()).where(AuditLog.created_at >= since, AuditLog.action.in_(actions))
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    got: dict[tuple[date, str], int] = {(d, a): n for d, a, n in db.execute(q.group_by(day, AuditLog.action)).all()}
    start = since.date()
    return [{"date": (start + timedelta(days=i)).isoformat(),
             **{a: got.get((start + timedelta(days=i), a), 0) for a in actions}} for i in range(DAYS)]


def overview(db: Session, user_id: uuid.UUID | None) -> dict:
    """user_id=None -> whole system (admin); otherwise one user's own data."""
    def scoped(q, col):
        return q.where(col == user_id) if user_id else q

    docs_by_status = dict(db.execute(scoped(select(Document.status, func.count()), Document.owner_id)
                                     .group_by(Document.status)).all())
    chunks = db.scalar(scoped(select(func.count()).select_from(DocumentChunk).join(Document, Document.id == DocumentChunk.document_id),
                              Document.owner_id))
    conv_q = scoped(select(func.count()).select_from(Conversation), Conversation.user_id)
    msg_base = select(func.count()).select_from(Message).join(Conversation, Conversation.id == Message.conversation_id)
    user_msgs = scoped(msg_base.where(Message.role == "user"), Conversation.user_id)
    asst = scoped(msg_base.where(Message.role == "assistant"), Conversation.user_id)
    lang_rows = db.execute(scoped(select(Message.detected_language, func.count())
                                  .join(Conversation, Conversation.id == Message.conversation_id)
                                  .where(Message.role == "user"), Conversation.user_id)
                           .group_by(Message.detected_language)).all()
    lat = db.execute(scoped(select(func.avg(Message.latency_ms), func.max(Message.latency_ms))
                            .join(Conversation, Conversation.id == Message.conversation_id)
                            .where(Message.role == "assistant", Message.latency_ms.is_not(None)), Conversation.user_id)).one()
    fb = dict(db.execute(scoped(select(UserFeedback.rating, func.count()), UserFeedback.user_id).group_by(UserFeedback.rating)).all())
    n_asst = db.scalar(asst) or 0
    n_insuff = db.scalar(asst.where(Message.insufficient_evidence.is_(True))) or 0
    modes = dict(db.execute(scoped(select(Message.retrieval_mode, func.count())
                                   .join(Conversation, Conversation.id == Message.conversation_id)
                                   .where(Message.role == "assistant", Message.retrieval_mode.is_not(None)), Conversation.user_id)
                            .group_by(Message.retrieval_mode)).all())
    last_eval = db.scalar(scoped(select(func.count()).select_from(EvaluationRun), EvaluationRun.owner_id)) or 0
    return {
        "documents": {"total": sum(docs_by_status.values()), "by_status": {s: docs_by_status.get(s, 0)
                      for s in ("pending", "processing", "ready", "failed")}},
        "chunks": chunks or 0,
        "conversations": db.scalar(conv_q) or 0,
        "messages": {"user": db.scalar(user_msgs) or 0, "assistant": n_asst, "insufficient_evidence": n_insuff},
        "language_usage": {(l or "unknown"): n for l, n in lang_rows},
        "retrieval_modes": modes,
        "latency_ms": {"avg": round(float(lat[0]), 1) if lat[0] is not None else None, "max": lat[1]},
        "feedback": {"up": fb.get(1, 0), "down": fb.get(-1, 0)},
        "activity": _daily(db, ("search", "chat"), user_id),
        "evaluation_runs": last_eval,
    }


def global_extras(db: Session) -> dict:
    users = db.scalar(select(func.count()).select_from(User)) or 0
    active = db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0
    failures = db.execute(select(Document.id, Document.title, Document.filename, ProcessingJob.error, ProcessingJob.finished_at)
                          .join(ProcessingJob, and_(ProcessingJob.document_id == Document.id, ProcessingJob.status == "failed"))
                          .where(Document.status == "failed").order_by(ProcessingJob.finished_at.desc()).limit(10)).all()
    return {"users": {"total": users, "active": active},
            "processing_failures": [{"document_id": str(i), "title": t, "filename": f, "error": e,
                                     "finished_at": at.isoformat() if at else None} for i, t, f, e, at in failures]}
