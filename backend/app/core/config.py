from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "IP-SAKTI Sahayaka API"
    environment: str = "development"  # development | production | test
    database_url: str = "postgresql+psycopg://sakti:sakti@localhost:5432/sakti"

    # Auth
    jwt_secret: str = "change-me-in-env-change-me-in-env-0000"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    # CORS: comma-separated origins
    cors_origins: str = "http://localhost:5173"

    # Rate limiting
    rate_limit_enabled: bool = True
    auth_rate_limit: str = "10/minute"

    # Embeddings (fixed per index; see docs/database.md)
    embedding_dim: int = 384
    embedding_provider: str = "local"  # local (sentence-transformers) | gemini (added at deployment phase)
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_batch_size: int = 32

    # LLM (Gemini). Model IDs change often: set GEMINI_MODEL explicitly and verify it with
    # `python -m app.scripts.check_llm` (lists the models your key can use).
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-flash-latest"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 1
    llm_temperature: float = 0.1
    llm_max_output_tokens: int = 4096

    # Reranking (optional cross-encoder; needs requirements-ml.txt). Verify the model on your machine.
    reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    rerank_candidates: int = 20

    # RAG answering
    query_rewrite_enabled: bool = True
    answer_top_k: int = 5
    max_context_chars: int = 12000
    max_history_turns: int = 6
    # Optional evidence gate: drop vector-only hits below this cosine similarity. None = disabled.
    # Must be calibrated on the real embedding model (Phase 7); deliberately off by default.
    min_evidence_similarity: float | None = None

    # Uploads and storage
    storage_dir: str = "storage"
    max_upload_mb: int = 20
    # Chunking (characters; chunks never cross page boundaries so page citations stay exact)
    chunk_size: int = 1000
    chunk_overlap: int = 150
    csv_rows_per_chunk: int = 10
    # OCR is only used for PDF pages with no text layer
    ocr_enabled: bool = True
    ocr_languages: str = "eng+hin+tel"

    @field_validator("jwt_secret")
    @classmethod
    def _secret_not_empty(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and s.jwt_secret.startswith("change-me-in-env"):
        raise RuntimeError("Set a strong JWT_SECRET in production")
    return s
