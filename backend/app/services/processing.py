"""Ingestion pipeline: extract -> clean -> chunk -> embed -> store. Runs as a background task."""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import SessionLocal
from app.document_processing.chunking import chunk_pages
from app.document_processing.cleaning import strip_repeated_headers_footers
from app.document_processing.extractors import extract
from app.document_processing.types import ExtractionError
from app.models import Document, DocumentChunk, ProcessingJob
from app.multilingual.detect import detect_language
from app.rag import embeddings

logger = logging.getLogger("sakti.processing")


def _now():
    return datetime.now(timezone.utc)


def _set_stage(db: Session, job: ProcessingJob, stage: str) -> None:
    job.stage = stage
    db.commit()


def process_document(document_id: uuid.UUID, job_id: uuid.UUID) -> None:
    """Never raises: failures are recorded on the document and job so the UI can show them."""
    s = get_settings()
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        job = db.get(ProcessingJob, job_id)
        if doc is None or job is None:
            return
        try:
            job.status, job.started_at, job.error = "running", _now(), None
            doc.status = "processing"
            db.commit()

            _set_stage(db, job, "extracting")
            result = extract(doc.storage_path, doc.source_type)

            _set_stage(db, job, "cleaning")
            pages = strip_repeated_headers_footers(result.pages)

            _set_stage(db, job, "chunking")
            chunks = chunk_pages(pages, s.chunk_size, s.chunk_overlap,
                                 one_chunk_per_page=doc.source_type in ("csv", "faq"))
            if not chunks:
                raise ExtractionError("No text remained after cleaning.")

            _set_stage(db, job, "embedding")
            vectors = embeddings.get_embedder().embed_passages([c.text for c in chunks])
            if len(vectors) != len(chunks):
                raise RuntimeError("Embedder returned a different number of vectors than chunks")

            _set_stage(db, job, "storing")
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))  # idempotent reprocess
            db.add_all(DocumentChunk(document_id=doc.id, chunk_index=c.index, page_number=c.page_number,
                                     section_heading=(c.section_heading or None) and c.section_heading[:255],
                                     text=c.text, language=c.language, embedding=v)
                       for c, v in zip(chunks, vectors))
            doc.page_count = result.page_count
            doc.language = detect_language(" ".join(c.text for c in chunks[:20]))
            doc.status = "ready"
            job.status, job.stage, job.finished_at = "succeeded", "done", _now()
            if result.warnings:
                job.error = "; ".join(result.warnings)  # non-fatal notes (e.g. OCR unavailable)
            db.commit()
        except ExtractionError as exc:
            db.rollback()
            _fail(db, document_id, job_id, str(exc))
        except Exception:
            logger.exception("Processing failed for document %s", document_id)
            db.rollback()
            _fail(db, document_id, job_id, "Processing failed unexpectedly. Please try re-uploading or contact an admin.")


def _fail(db: Session, document_id: uuid.UUID, job_id: uuid.UUID, message: str) -> None:
    doc, job = db.get(Document, document_id), db.get(ProcessingJob, job_id)
    if doc:
        doc.status = "failed"
    if job:
        job.status, job.error, job.finished_at = "failed", message, _now()
    db.commit()
