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
