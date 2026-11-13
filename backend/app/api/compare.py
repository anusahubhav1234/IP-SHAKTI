from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.search import _validate_documents
from app.core.limiter import limiter
from app.database.session import get_db
from app.models import Document, User
from app.rag.llm import LLMError
from app.schemas.compare import CompareRequest, CompareResponse
from app.services.audit import log_action
from app.services.comparison import compare_documents

router = APIRouter(prefix="/api/documents", tags=["comparison"])
_LLM_STATUS = {"rate_limited": 429, "blocked": 422, "bad_response": 502, "auth": 503, "not_configured": 503, "unavailable": 503}


@router.post("/compare", response_model=CompareResponse)
@limiter.limit("10/minute")
def compare(request: Request, body: CompareRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = _validate_documents(db, user, body.document_ids)
    if len(ids) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Select at least two different documents")
    by_id = {d.id: d for d in db.scalars(select(Document).where(Document.id.in_(ids)))}
    try:
        res = compare_documents(db, user, [by_id[i] for i in ids], body.aspects, body.language)
    except LLMError as exc:
        log_action(db, action="compare_error", user_id=user.id, request=request, details={"kind": exc.kind})
        db.commit()
        raise HTTPException(_LLM_STATUS.get(exc.kind, 503), str(exc))
    log_action(db, action="compare", user_id=user.id, request=request,
               details={"documents": len(ids), "status": res.status, "latency_ms": res.latency_ms})
    db.commit()
    return res
