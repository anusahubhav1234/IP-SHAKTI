import uuid

from app.rag.types import Hit

RRF_K = 60  # standard constant from Cormack et al. (2009); damps the influence of top ranks


def reciprocal_rank_fusion(rankings: list[list[Hit]], k: int = RRF_K) -> list[Hit]:
    """score(d) = sum over rankers of 1 / (k + rank_r(d)), ranks are 1-based.

    RRF uses ranks only, so it needs no score normalisation between cosine similarity and BM25
    (which live on incomparable scales). Each ranking's Hit objects may carry their own
    vector_/bm25_ fields; these are merged onto one Hit per chunk."""
    merged: dict[uuid.UUID, Hit] = {}
    fused: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
            m = merged.get(hit.chunk_id)
            if m is None:
                merged[hit.chunk_id] = hit
            else:
                if hit.vector_rank is not None:
                    m.vector_rank, m.vector_score = hit.vector_rank, hit.vector_score
                if hit.bm25_rank is not None:
                    m.bm25_rank, m.bm25_score = hit.bm25_rank, hit.bm25_score
    for cid, hit in merged.items():
        hit.score = fused[cid]
    return sorted(merged.values(), key=lambda h: (-h.score, str(h.chunk_id)))
