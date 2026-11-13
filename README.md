# IP-SAKTI Sahayaka 2.0
Multilingual, RAG-based, source-cited AI assistant (B.Tech IT major project).
Status: **All phases built** (backend + React frontend). 155 backend tests pass; the frontend builds but has no automated tests; live Gemini, real embedding/reranker models, Docker and Hindi/Telugu OCR are untested here. See `docs/database.md`.

## Run locally (backend)
```bash
cp .env.example .env            # set JWT_SECRET (32+ chars)
docker compose up -d db         # Postgres 16 + pgvector
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-ml.txt   # real embeddings (PyTorch); first run downloads the model (~120 MB)
sudo apt install tesseract-ocr tesseract-ocr-hin tesseract-ocr-tel   # optional: OCR for scanned PDFs
export $(grep -v '^#' ../.env | xargs)
alembic upgrade head
python -m app.scripts.create_admin you@example.com "Your Name"
uvicorn app.main:app --reload   # Swagger UI: http://localhost:8000/docs
```
Or everything in Docker: `docker compose up --build`.

## Tests
Create a `sakti_test` database (same server), then: `cd backend && DATABASE_URL=postgresql+psycopg://sakti:sakti@localhost:5432/sakti_test pytest`


More: `docs/architecture.md`, `docs/api-documentation.md`, `docs/deployment.md`.
