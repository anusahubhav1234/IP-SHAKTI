# API

Interactive docs: `/docs` (Swagger) when the backend is running. All routes except `/api/auth/register`, `/api/auth/login`
and `/health` need `Authorization: Bearer <token>`.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register, /login, /logout, /change-password`; `GET/PATCH /api/auth/me` |
| Documents | `GET/POST /api/documents`, `GET/DELETE /api/documents/{id}`, `/status`, `/chunks`, `/file`, `POST /reprocess`, `POST /api/documents/compare`; `GET/POST /api/categories` |
| Search | `POST /api/search` (modes: vector, bm25, hybrid, hybrid_rerank) |
| Chat | `POST /api/chat`, `POST /api/chat/stream` (SSE stages), `GET /api/conversations`, `GET/DELETE /api/conversations/{id}`, `POST/DELETE /api/messages/{id}/feedback` |
| Analytics | `GET /api/analytics/overview, /evaluation` |
| Evaluation | `GET/POST /api/evaluation/benchmarks`, `POST /api/evaluation/runs`, `GET /api/evaluation/runs` |
| Admin | `GET /api/admin/overview, /users, /documents, /system-health`; `PATCH /api/admin/users/{id}` |
