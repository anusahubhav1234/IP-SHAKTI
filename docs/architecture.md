# Architecture

```
Browser (React/Vite)  --JWT-->  FastAPI  -->  PostgreSQL 16 + pgvector
                                  |--> Embeddings (sentence-transformers locally, or a hosted API)
                                  |--> Gemini REST API (answers, query rewrite, comparison)
                                  |--> Tesseract OCR (eng+hin+tel) for scanned pages
```

**Ingestion** (BackgroundTasks, no Celery): upload -> extract (PDF/DOCX/TXT/CSV, OCR fallback) -> NFC clean -> page-aware chunking
(chunks never cross pages) -> embeddings -> pgvector. Status is polled via `/api/documents/{id}/status`.

**Answering**: optional follow-up rewrite -> retrieval (vector, BM25, hybrid RRF k=60, optional cross-encoder rerank) ->
Gemini with fenced, untrusted SOURCE blocks -> citation verification (each quote must occur in the cited chunk) -> answer,
`insufficient_evidence`, or `unverified_withheld`. Raw model tokens are never streamed; SSE sends progress stages only.

**Security**: bcrypt, JWT (role re-read from DB on each request), per-user document isolation, slowapi rate limits,
audit log that never stores question text, upload type/size checks. The API key lives only in server environment variables.

See `rag-pipeline.md` and `database.md` for detail.
