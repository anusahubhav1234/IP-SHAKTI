"""Embedding providers behind one interface.

The vector dimension is fixed by the pgvector column (EMBEDDING_DIM); an embedder whose output
dimension differs is rejected at load time rather than silently corrupting the index.
E5 models need 'passage: ' / 'query: ' prefixes; the interface exposes both methods so callers
cannot forget them."""
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings


class Embedder(ABC):
    dim: int

    @abstractmethod
    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


class LocalE5Embedder(Embedder):
    def __init__(self, model_name: str, batch_size: int):
        # Imported lazily: sentence-transformers pulls in PyTorch (see requirements-ml.txt).
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name, device="cpu")
        self.dim = self._model.get_sentence_embedding_dimension()
        self._batch = batch_size
        expected = get_settings().embedding_dim
        if self.dim != expected:
            raise RuntimeError(f"Model outputs {self.dim}-dim vectors but the database column is {expected}-dim")

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, batch_size=self._batch, normalize_embeddings=True,
                                  show_progress_bar=False)
        return [v.tolist() for v in vecs]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode([f"passage: {t}" for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}"])[0]


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_provider == "local":
        return LocalE5Embedder(s.embedding_model, s.embedding_batch_size)
    raise RuntimeError(f"Unknown EMBEDDING_PROVIDER '{s.embedding_provider}'")
