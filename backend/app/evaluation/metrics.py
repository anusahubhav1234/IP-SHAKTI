"""Retrieval metrics with binary, page-level relevance.

Gold = a set of "units" (document_id, page_number); page_number None means "any page of that document".
Credit-once rule: a gold unit is credited only by the FIRST retrieved chunk that matches it; later chunks
from the same page count as non-relevant. This keeps every metric within [0, 1]."""
import math
from dataclasses import dataclass

Unit = tuple[str, int | None]


@dataclass(frozen=True)
class Retrieved:
    document_id: str
    page_number: int | None


def relevance_vector(retrieved: list[Retrieved], gold: list[Unit], k: int) -> list[int]:
    remaining = list(dict.fromkeys(gold))
    rel = []
    for r in retrieved[:k]:
        match = next((g for g in remaining if g[0] == r.document_id and (g[1] is None or g[1] == r.page_number)), None)
        if match is not None:
            remaining.remove(match)
            rel.append(1)
        else:
            rel.append(0)
    return rel


def precision_at_k(rel: list[int], k: int) -> float:
    return sum(rel[:k]) / k


def recall_at_k(rel: list[int], n_gold: int, k: int) -> float:
    return sum(rel[:k]) / n_gold if n_gold else 0.0


def reciprocal_rank(rel: list[int]) -> float:
    for i, r in enumerate(rel, start=1):
        if r:
            return 1.0 / i
    return 0.0


def ndcg_at_k(rel: list[int], n_gold: int, k: int) -> float:
    dcg = sum(r / math.log2(i + 1) for i, r in enumerate(rel[:k], start=1))
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(k, n_gold) + 1))
    return dcg / ideal if ideal else 0.0


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]
