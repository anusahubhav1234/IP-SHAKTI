import json
import queue
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.search import _validate_documents
from app.core.limiter import limiter
from app.database.session import get_db
from app.database.session import SessionLocal
from app.models import Conversation, Message, User, UserFeedback
from app.rag.llm import LLMError
from app.schemas.chat import (ChatRequest, ChatResponse, CitationOut, ConversationDetail, ConversationList,
                              ConversationOut, FeedbackIn, FeedbackOut, MessageOut)
from app.services.answering import answer_question, get_owned_conversation, open_url
from app.services.audit import log_action

router = APIRouter(prefix="/api", tags=["chat"])

_LLM_STATUS = {"rate_limited": 429, "blocked": 422, "bad_response": 502, "auth": 503,
               "not_configured": 503, "unavailable": 503}


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
def chat(request: Request, body: ChatRequest, user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    if not body.message.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Message cannot be blank")
    doc_ids = _validate_documents(db, user, body.document_ids)
    try:
        r = answer_question(db, user, body.message, conversation_id=body.conversation_id, language=body.language,
                            mode=body.mode, top_k=body.top_k, doc_ids=doc_ids, request=request)
    except LLMError as exc:
        db.rollback()
        log_action(db, action="chat_error", user_id=user.id, request=request, details={"kind": exc.kind})
        db.commit()
        # exc messages are written to be user-safe (no keys, URLs or provider internals)
        raise HTTPException(_LLM_STATUS.get(exc.kind, 503), str(exc))
    return _response(r)


def _response(r) -> ChatResponse:
    return ChatResponse(
        conversation_id=r.conversation.id, message_id=r.message.id, answer=r.message.content, status=r.status,
        insufficient_evidence=r.status != "answered", language=r.language, detected_language=r.detected_language,
        retrieval_mode=r.mode, rewritten_query=r.rewritten_query,
        citations=[CitationOut(**c.__dict__) for c in r.citations], latency_ms=r.latency_ms,
        timings_ms=r.timings_ms)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
@limiter.limit("20/minute")
def chat_stream(request: Request, body: ChatRequest, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Server-Sent Events. Streams pipeline *progress* (rewriting, retrieving, generating, verifying) and then
    the final verified answer in one `result` event. Raw model tokens are deliberately NOT streamed: the answer is
    only shown after its citations were verified, and streaming unverified text would break that guarantee."""
    if not body.message.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Message cannot be blank")
    doc_ids = _validate_documents(db, user, body.document_ids)  # plain HTTP errors before the stream starts
    if body.conversation_id:
        get_owned_conversation(db, user, body.conversation_id)
    user_id = user.id
    q: queue.Queue = queue.Queue()

    def worker():
        try:
            with SessionLocal() as wdb:  # own session: the request-scoped one is not safe to use from this thread
                wuser = wdb.get(User, user_id)
                try:
                    r = answer_question(wdb, wuser, body.message, conversation_id=body.conversation_id,
                                        language=body.language, mode=body.mode, top_k=body.top_k, doc_ids=doc_ids,
                                        request=request, on_stage=lambda name: q.put(("stage", {"stage": name})))
                    q.put(("result", json.loads(_response(r).model_dump_json())))
                except LLMError as exc:
                    wdb.rollback()
                    log_action(wdb, action="chat_error", user_id=user_id, request=request, details={"kind": exc.kind})
                    wdb.commit()
                    q.put(("error", {"status": _LLM_STATUS.get(exc.kind, 503), "detail": str(exc)}))
        except Exception:
            q.put(("error", {"status": 500, "detail": "Internal server error"}))
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def events():
        yield _sse("stage", {"stage": "started"})
        while (item := q.get()) is not None:
            yield _sse(*item)
        yield _sse("done", {})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/messages/{message_id}/feedback", response_model=FeedbackOut)
def give_feedback(message_id: uuid.UUID, body: FeedbackIn, request: Request,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Thumbs up/down on an assistant message in the caller's own conversation (one rating per user per message)."""
    msg = _own_assistant_message(db, user, message_id)
    fb = db.scalar(select(UserFeedback).where(UserFeedback.message_id == msg.id, UserFeedback.user_id == user.id))
    if fb is None:
        fb = UserFeedback(message_id=msg.id, user_id=user.id, rating=body.rating, comment=body.comment)
        db.add(fb)
    else:
        fb.rating, fb.comment = body.rating, body.comment
    log_action(db, action="feedback", user_id=user.id, entity_type="message", entity_id=str(msg.id),
               request=request, details={"rating": body.rating})
    db.commit()
    return FeedbackOut(message_id=msg.id, rating=fb.rating, comment=fb.comment)


@router.delete("/messages/{message_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
def remove_feedback(message_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    msg = _own_assistant_message(db, user, message_id)
    fb = db.scalar(select(UserFeedback).where(UserFeedback.message_id == msg.id, UserFeedback.user_id == user.id))
    if fb:
        db.delete(fb)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _own_assistant_message(db: Session, user: User, message_id: uuid.UUID) -> Message:
    msg = db.get(Message, message_id)
    conv = db.get(Conversation, msg.conversation_id) if msg else None
    if msg is None or conv is None or conv.user_id != user.id or msg.role != "assistant":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return msg


@router.get("/conversations", response_model=ConversationList)
def list_conversations(limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    base = select(Conversation).where(Conversation.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(base.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)).all()
    return ConversationList(items=[ConversationOut.model_validate(c) for c in rows], total=total)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: uuid.UUID, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    conv = get_owned_conversation(db, user, conversation_id)
    ratings = dict(db.execute(select(UserFeedback.message_id, UserFeedback.rating)
                              .where(UserFeedback.user_id == user.id,
                                     UserFeedback.message_id.in_([m.id for m in conv.messages]))).all())
    messages = []
    for m in conv.messages:
        out = MessageOut.model_validate(m)
        out.my_feedback = ratings.get(m.id)
        out.citations = [CitationOut(number=i, chunk_id=c.chunk_id, document_id=c.document_id,
                                     document_title=c.document_title, page_number=c.page_number,
                                     excerpt=c.excerpt, verified=c.verified, retrieval_score=c.retrieval_score,
                                     open_url=open_url(c.document_id, c.page_number))
                         for i, c in enumerate(sorted(m.citations, key=lambda c: c.created_at), start=1)]
        messages.append(out)
    return ConversationDetail(id=conv.id, title=conv.title, created_at=conv.created_at,
                              updated_at=conv.updated_at, messages=messages)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: uuid.UUID, request: Request, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    conv = get_owned_conversation(db, user, conversation_id)
    log_action(db, action="conversation.delete", user_id=user.id, entity_type="conversation",
               entity_id=str(conv.id), request=request)
    db.delete(conv)  # messages, citations, feedback cascade in the database
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
