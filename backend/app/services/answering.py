"""RAG answer pipeline: detect language -> retrieve -> build prompt -> LLM -> verify citations -> persist.

Guarantees (each covered by tests): the LLM is not called when nothing was retrieved; an answer none of
whose citations can be verified is withheld; page numbers/titles come from the database, not the model;
the question text is never written to the audit log."""
import logging
import time
import uuid
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Citation, Conversation, Message, User
from app.multilingual.detect import detect_language
from app.rag.llm import ANSWER_SCHEMA, get_llm_client, parse_llm_answer
from app.rag.prompting import build_prompt
from app.rag.retriever import retrieve
from app.rag.rewrite import rewrite_query
from app.rag.types import Hit
from app.rag.verification import verify_answer
from app.services.audit import log_action

logger = logging.getLogger("sakti.answering")

# NOTE: the Hindi and Telugu strings below should be reviewed by a native speaker before the final demo.
NO_EVIDENCE = {
    "en": "The available documents do not contain enough information to answer this question.",
    "hi": "उपलब्ध दस्तावेज़ों में इस प्रश्न का उत्तर देने के लिए पर्याप्त जानकारी नहीं है।",
    "te": "అందుబాటులో ఉన్న పత్రాలలో ఈ ప్రశ్నకు సమాధానం ఇవ్వడానికి తగినంత సమాచారం లేదు.",
}
UNVERIFIED = {
    "en": "I could not verify an answer against your documents, so I am not showing one. Please try rephrasing the question.",
    "hi": "मैं आपके दस्तावेज़ों के आधार पर उत्तर सत्यापित नहीं कर सका, इसलिए उत्तर नहीं दिखा रहा हूँ। कृपया प्रश्न दोबारा पूछें।",
    "te": "మీ పత్రాల ఆధారంగా సమాధానాన్ని ధృవీకరించలేకపోయాను, కాబట్టి సమాధానం చూపడం లేదు. దయచేసి ప్రశ్నను మళ్లీ అడగండి.",
}


@dataclass
class CitationView:
    number: int | None
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    document_title: str
    page_number: int | None
    section_heading: str | None
    excerpt: str
    verified: bool
    retrieval_score: float | None
    open_url: str | None


@dataclass
class ChatResult:
    rewritten_query: str | None
    conversation: Conversation
    message: Message
    status: str
    language: str
    detected_language: str
    mode: str
    citations: list[CitationView]
    latency_ms: int
    timings_ms: dict[str, float]


def open_url(document_id: uuid.UUID | None, page: int | None) -> str | None:
    if document_id is None:
        return None
    return f"/api/documents/{document_id}/file" + (f"#page={page}" if page else "")


def get_owned_conversation(db: Session, user: User, conversation_id: uuid.UUID) -> Conversation:
    from fastapi import HTTPException, status
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:  # 404, not 403: do not reveal other users' ids
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


def _evidence_gate(hits: list[Hit]) -> list[Hit]:
    """Optional similarity floor (off unless MIN_EVIDENCE_SIMILARITY is set after calibration)."""
    floor = get_settings().min_evidence_similarity
    if floor is None:
        return hits
    return [h for h in hits if h.bm25_rank is not None or (h.vector_score is not None and h.vector_score >= floor)]


def _history(conv: Conversation | None) -> list[dict]:
    if conv is None:
        return []
    return [{"role": m.role, "content": m.content} for m in conv.messages if m.content]


def answer_question(db: Session, user: User, question: str, *, conversation_id: uuid.UUID | None = None,
                    language: str | None = None, mode: str = "hybrid", top_k: int | None = None,
                    doc_ids: list[uuid.UUID] | None = None, request: Request | None = None,
                    on_stage=None) -> ChatResult:
    """`on_stage(name)` is called as the pipeline advances (used by the streaming endpoint)."""
    stage = on_stage or (lambda _name: None)
    s = get_settings()
    t0 = time.perf_counter()
    question = question.strip()
    detected = detect_language(question)
    out_lang = language or detected
    conv = get_owned_conversation(db, user, conversation_id) if conversation_id else None
    history = _history(conv)

    search_query = question
    if history:
        stage("rewriting")
        search_query = rewrite_query(question, history)
    stage("retrieving")
    retrieval = retrieve(db, user.id, search_query, mode=mode, top_k=top_k or s.answer_top_k, doc_ids=doc_ids)
    hits = _evidence_gate(retrieval.hits)
    timings = dict(retrieval.timings_ms)

    status_, answer_text, citations, removed = "insufficient_evidence", NO_EVIDENCE[out_lang], [], 0
    if hits:  # never call the LLM with no evidence
        prompt = build_prompt(question, out_lang, hits, history)
        stage("generating")
        t = time.perf_counter()
        result = get_llm_client().generate_json(prompt.system, prompt.user, ANSWER_SCHEMA)  # LLMError propagates
        timings["llm"] = round((time.perf_counter() - t) * 1000, 1)
        stage("verifying")
        parsed = parse_llm_answer(result.text)
        if parsed.insufficient_evidence or not parsed.answer.strip():
            pass
        else:
            ver = verify_answer(parsed, prompt.sources)
            removed = ver.removed_markers
            if ver.verified_count == 0:
                status_, answer_text = "unverified_withheld", UNVERIFIED[out_lang]
                logger.info("Answer withheld: no citation could be verified")
            else:
                status_, answer_text = "answered", ver.answer
                citations = [CitationView(c.number, c.hit.chunk_id, c.hit.document_id, c.hit.document_title,
                                          c.hit.page_number, c.hit.section_heading,
                                          (c.quote if c.verified and c.quote else c.hit.text[:300]),
                                          c.verified, c.hit.score, open_url(c.hit.document_id, c.hit.page_number))
                             for c in ver.citations]

    latency_ms = int((time.perf_counter() - t0) * 1000)
    if conv is None:
        conv = Conversation(user_id=user.id, title=question[:60] or "New conversation")
        db.add(conv)
        db.flush()
    db.add(Message(conversation_id=conv.id, role="user", content=question, detected_language=detected,
                   response_language=out_lang))
    msg = Message(conversation_id=conv.id, role="assistant", content=answer_text, detected_language=detected,
                  response_language=out_lang, retrieval_mode=mode, latency_ms=latency_ms,
                  insufficient_evidence=status_ != "answered")
    db.add(msg)
    db.flush()
    for c in citations:
        db.add(Citation(message_id=msg.id, chunk_id=c.chunk_id, document_id=c.document_id,
                        document_title=c.document_title, page_number=c.page_number, excerpt=c.excerpt,
                        retrieval_score=c.retrieval_score, verified=c.verified))
    log_action(db, action="chat", user_id=user.id, entity_type="conversation", entity_id=str(conv.id),
               request=request, details={"status": status_, "mode": mode, "language": out_lang,
                                         "detected_language": detected, "latency_ms": latency_ms,
                                         "sources": len(hits), "removed_markers": removed,
                                         "rewritten": search_query != question})
    db.commit()
    return ChatResult(search_query if search_query != question else None, conv, msg, status_, out_lang, detected, mode, citations, latency_ms,
                      {**timings, "total": float(latency_ms)})
