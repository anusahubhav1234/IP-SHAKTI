"""Runs a benchmark through the SAME retrieve() used by the product, once per retrieval mode.
Only real measurements are returned: nothing is estimated or filled in."""
import logging
import time
import uuid
from statistics import mean

from sqlalchemy.orm import Session

from app.evaluation import metrics as m
from app.rag.reranker import RerankerUnavailable
from app.rag.retriever import retrieve

logger = logging.getLogger("sakti.eval")


def _gold(item: dict) -> list[m.Unit]:
    return [(g["document_id"], g.get("page")) for g in item.get("relevant", [])]


def evaluate_mode(db: Session, user_id: uuid.UUID, items: list[dict], mode: str, top_k: int) -> dict:
    per_item, latencies = [], []
    for it in items:
        gold = _gold(it)
        if not gold:  # unanswerable question: no gold passages, excluded from retrieval metrics
            continue
        t = time.perf_counter()
        res = retrieve(db, user_id, it["question"], mode=mode, top_k=top_k)
        latencies.append((time.perf_counter() - t) * 1000)
        rel = m.relevance_vector([m.Retrieved(str(h.document_id), h.page_number) for h in res.hits], gold, top_k)
        per_item.append({"question": it["question"], "language": it.get("language", "en"),
                         "precision": m.precision_at_k(rel, top_k), "recall": m.recall_at_k(rel, len(set(gold)), top_k),
                         "rr": m.reciprocal_rank(rel), "ndcg": m.ndcg_at_k(rel, len(set(gold)), top_k),
                         "first_relevant_rank": next((i for i, r in enumerate(rel, 1) if r), None)})

    def agg(rows):
        if not rows:
            return None
        return {"n": len(rows), f"precision@{top_k}": round(mean(r["precision"] for r in rows), 4),
                f"recall@{top_k}": round(mean(r["recall"] for r in rows), 4),
                "mrr": round(mean(r["rr"] for r in rows), 4), f"ndcg@{top_k}": round(mean(r["ndcg"] for r in rows), 4)}

    langs = sorted({r["language"] for r in per_item})
    return {"mode": mode, "overall": agg(per_item), "by_language": {l: agg([r for r in per_item if r["language"] == l]) for l in langs},
            "latency_ms": {"mean": round(mean(latencies), 1), "p95": round(m.percentile(latencies, 95), 1)} if latencies else None,
            "items": per_item}


def run_evaluation(db: Session, user_id: uuid.UUID, items: list[dict], modes: list[str], top_k: int) -> dict:
    out = {}
    for mode in modes:
        try:
            out[mode] = evaluate_mode(db, user_id, items, mode, top_k)
        except RerankerUnavailable as exc:
            logger.info("Mode %s skipped: %s", mode, exc)
            out[mode] = {"mode": mode, "error": "Reranker is not available on this server; mode not evaluated."}
    return {"top_k": top_k, "n_questions": len(items), "n_scored": sum(1 for i in items if i.get("relevant")),
            "modes": out}
