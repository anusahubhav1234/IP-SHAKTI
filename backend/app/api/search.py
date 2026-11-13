import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.limiter import limiter
from app.database.session import get_db
from app.models import Document, User
from app.multilingual.detect import detect_language
from app.rag.retriever import retrieve
from app.schemas.search import HybridSearchRequest, SearchHit, SearchRequest, SearchResponse
from app.services.audit import log_action

router = APIRouter(prefix="/api/search", tags=["search"])


def _validate_documents(db: Session, user: User, ids) -> list | None:
    """Searches only ever cover the caller's own ready documents; anything else is reported as not found."""
    if not ids:
        return None
    ids = list(dict.fromkeys(ids))
    found = set(db.scalars(select(Document.id).where(Document.id.in_(ids), Document.owner_id == user.id,
                                                      Document.status == "ready")).all())
    if found != set(ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more documents were not found or are not ready")
    return ids


def _run(db: Session, user: User, request: Request, query: str, mode: str, top_k: int, doc_ids) -> SearchResponse:
    query = query.strip()
    if not query:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Query cannot be blank")
    doc_ids = _validate_documents(db, user, doc_ids)
    t0 = time.perf_counter()
    result = retrieve(db, user.id, query, mode=mode, top_k=top_k, doc_ids=doc_ids)
    total_ms = round((time.perf_counter() - t0) * 1000, 1)
    lang = detect_language(query)
    # Query text is deliberately NOT stored; only aggregate-friendly metadata for the admin dashboard.
    log_action(db, action="search", user_id=user.id, request=request,
               details={"mode": mode, "language": lang, "results": len(result.hits), "latency_ms": total_ms})
    db.commit()
    return SearchResponse(query=query, detected_language=lang, mode=mode, top_k=top_k,
                          results=[SearchHit(**{k: getattr(h, k) for k in SearchHit.model_fields}) for h in result.hits],
                          timings_ms={**result.timings_ms, "total": total_ms})


@router.post("", response_model=SearchResponse)
@limiter.limit("60/minute")
def search(request: Request, body: SearchRequest, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    """Single-mode search. Default 'vector' is the semantic baseline used for comparison."""
    return _run(db, user, request, body.query, body.mode, body.top_k, body.document_ids)


@router.post("/hybrid", response_model=SearchResponse)
@limiter.limit("60/minute")
def search_hybrid(request: Request, body: HybridSearchRequest, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Vector + BM25 fused with Reciprocal Rank Fusion."""
    return _run(db, user, request, body.query, "hybrid", body.top_k, body.document_ids)
