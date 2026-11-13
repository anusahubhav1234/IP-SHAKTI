from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def log_action(db: Session, *, action: str, user_id=None, entity_type: str | None = None,
               entity_id: str | None = None, request: Request | None = None,
               details: dict | None = None) -> None:
    """Adds an audit row to the current session; the caller commits."""
    db.add(AuditLog(user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id,
                    ip_address=client_ip(request), details=details))
