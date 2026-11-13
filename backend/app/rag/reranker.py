"""Optional cross-encoder reranker. It scores (query, passage) pairs jointly, which is more accurate than the
bi-encoder used for retrieval but far slower, so it only reorders the ~20 fused candidates.
Needs sentence-transformers (requirements-ml.txt) and downloads the model on first use."""
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings


class RerankerUnavailable(Exception):
    """Raised when reranking is requested but the model/library cannot be loaded."""


class Reranker(ABC):
    @abstractmethod
    def score(self, query: str, passages: list[str]) -> list[float]: ...


class CrossEncoderReranker(Reranker):
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(model_name, device="cpu", max_length=512)
        except Exception as exc:  # missing package, offline, unknown model
            raise RerankerUnavailable(f"Reranker could not be loaded: {type(exc).__name__}") from exc

    def score(self, query: str, passages: list[str]) -> list[float]:
        return [float(x) for x in self._model.predict([(query, p) for p in passages], show_progress_bar=False)]


@lru_cache
def get_reranker() -> Reranker:
    return CrossEncoderReranker(get_settings().reranker_model)
