import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import admin, analytics, auth, chat, compare, documents, evaluation, health, search
from app.core.config import get_settings
from app.core.limiter import limiter
from app.rag.reranker import RerankerUnavailable

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sakti")

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0",
              docs_url=None if settings.is_production else "/docs",
              redoc_url=None if settings.is_production else "/redoc")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,  # bearer tokens in headers, not cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(RerankerUnavailable)
async def reranker_unavailable_handler(request: Request, exc: RerankerUnavailable):
    return JSONResponse(status_code=503, content={"detail": "The reranker is not available on this server."})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(compare.router)
app.include_router(evaluation.router)
app.include_router(analytics.router)
app.include_router(admin.router)
