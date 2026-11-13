# Deployment

## Local (Docker)
```
cp .env.example .env      # set JWT_SECRET (long random) and GEMINI_API_KEY
docker compose up --build
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.create_admin
docker compose exec backend python -m app.scripts.check_llm   # real Gemini check
```
Frontend: http://localhost:5173, API: http://localhost:8000/docs. Docker was **not** tested in the build environment.

## Hosted (suggested)
- **Database**: Neon (or any Postgres 16 with the `vector` extension). Set `DATABASE_URL` (`postgresql+psycopg://...`), run `alembic upgrade head`.
- **Backend**: Render web service from `backend/Dockerfile`. Env: `DATABASE_URL`, `JWT_SECRET`, `GEMINI_API_KEY`, `CORS_ORIGINS=https://<your-frontend>`, `ENVIRONMENT=production`.
  Free tiers have little RAM: use a hosted embedding provider rather than loading sentence-transformers, and note that uploaded files on ephemeral disks are lost on redeploy (attach a disk or move storage to object storage).
- **Frontend**: Vercel/Netlify, build `npm run build`, output `dist`, env `VITE_API_URL=https://<your-backend>`. Add an SPA fallback rewrite to `index.html`.
- Rotate any key that was ever pasted into chat or committed.

## Vercel multi-service deployment
The root `vercel.json` deploys the `backend` FastAPI service and `frontend` Vite service together. Requests to `/api/*` are publicly rewritten to the backend; all other paths go to the frontend. In production the frontend uses same-origin `/api` requests when `VITE_API_URL` is unset; local development still defaults to `http://localhost:8000`.

Set `DATABASE_URL`, a unique `JWT_SECRET` (at least 32 characters), and `GEMINI_API_KEY` in Vercel's backend service environment. Use hosted PostgreSQL with pgvector enabled and apply migrations with `alembic upgrade head` before serving traffic. Configure `ENVIRONMENT=production`. The app currently relies on local sentence-transformers for embeddings and local filesystem storage for uploads. Vercel's serverless filesystem is ephemeral, so document uploads will not be durable; the Python ML dependencies and OCR system packages are also not included by the default Vercel build. These features need a compatible external embedding/storage setup or a separately hosted backend before production use.

The browser calls the backend through the public `/api/*` rewrite, so neither service needs an internal service binding. No server-side service-to-service calls currently exist.
