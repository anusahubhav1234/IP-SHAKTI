import math

import pytest
from sqlalchemy import text

from app.database.session import engine
from app.evaluation import metrics as m
from app.rag.reranker import RerankerUnavailable
from tests.fakes import OverlapReranker, install_llm, find_source
from tests.helpers import make_pdf

PAGES = ["Attendance rules. Students must maintain 75 percent attendance to appear for examinations.",
         "Condonation. Students with attendance shortage between 65 and 75 percent may apply for condonation fee.",
         "Fee schedule. The fee payment deadline is 15 March for all semesters."]
PLACEMENT = b"Acme Corp placement drive. Eligibility: minimum 60 percent marks and no active backlogs."


# ------------------------------------------------------------------ metric maths (hand-computed)

def test_metrics_match_hand_calculation():
    rel = [0, 1, 0, 1, 0]
    assert m.precision_at_k(rel, 5) == pytest.approx(0.4)
    assert m.recall_at_k(rel, 2, 5) == pytest.approx(1.0)
    assert m.reciprocal_rank(rel) == pytest.approx(0.5)
    dcg = 1 / math.log2(3) + 1 / math.log2(5)
    ideal = 1 + 1 / math.log2(3)
    assert m.ndcg_at_k(rel, 2, 5) == pytest.approx(dcg / ideal)
    assert m.ndcg_at_k([1, 1], 2, 5) == pytest.approx(1.0)
    assert m.ndcg_at_k([0, 0, 0], 2, 3) == 0 and m.reciprocal_rank([0, 0]) == 0 and m.recall_at_k([], 0, 5) == 0


def test_relevance_credit_once_and_page_matching():
    R = m.Retrieved
    gold = [("d1", 2)]
    assert m.relevance_vector([R("d1", 2), R("d1", 2), R("d2", 2)], gold, 5) == [1, 0, 0]  # duplicates not double counted
    assert m.relevance_vector([R("d1", 1), R("d1", 2)], gold, 5) == [0, 1]                   # wrong page is a miss
    assert m.relevance_vector([R("d1", 9), R("d1", 3)], [("d1", None)], 5) == [1, 0]          # None = any page, still once
    assert m.relevance_vector([R("d1", 1), R("d2", 4)], [("d1", 1), ("d2", 4), ("d3", 1)], 5) == [1, 1]
    assert m.relevance_vector([R("d1", 1), R("d1", 1)], [("d1", 1), ("d1", 1)], 5) == [1, 0]  # duplicate gold collapsed
    assert m.relevance_vector([R("d1", 1)] * 6, [("d1", 1)], 3) == [1, 0, 0]                  # truncated to k


def test_percentile_nearest_rank():
    assert m.percentile(list(map(float, range(1, 21))), 95) == 19.0
    assert m.percentile([5.0], 95) == 5.0 and m.percentile([], 95) == 0.0


# ------------------------------------------------------------------ reranker mode

@pytest.fixture
def alice(auth_headers):
    return auth_headers("alice@example.com")


@pytest.fixture
def bob(client, make_user):
    make_user(email="bob@example.com")
    r = client.post("/api/auth/login", json={"email": "bob@example.com", "password": "Password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def up(client, headers, name, data):
    r = client.post("/api/documents/upload", headers=headers, files={"file": (name, data)})
    assert r.status_code == 202, r.text
    return r.json()["id"]


@pytest.fixture
def corpus(client, alice):
    return {"reg": up(client, alice, "regulations.pdf", make_pdf(PAGES)), "plc": up(client, alice, "placement.txt", PLACEMENT)}


@pytest.fixture
def reranker(monkeypatch):
    monkeypatch.setattr("app.rag.retriever.get_reranker", lambda: OverlapReranker())


def search(client, headers, query, mode, **kw):
    return client.post("/api/search", headers=headers, json={"query": query, "mode": mode, **kw})


def test_rerank_mode_reorders_by_cross_encoder_score(client, alice, corpus, reranker):
    r = search(client, alice, "attendance shortage condonation fee", "hybrid_rerank", top_k=3).json()
    assert r["mode"] == "hybrid_rerank" and "rerank" in r["timings_ms"]
    scores = [h["rerank_score"] for h in r["results"]]
    assert scores == sorted(scores, reverse=True) and all(s is not None for s in scores)
    assert r["results"][0]["page_number"] == 2 and r["results"][0]["rerank_score"] == 4.0
    assert all(h["score"] == h["rerank_score"] for h in r["results"])
    assert all(h["vector_rank"] is not None or h["bm25_rank"] is not None for h in r["results"])  # provenance kept


def test_rerank_unavailable_is_a_safe_503(client, alice, corpus, monkeypatch):
    def broken():
        raise RerankerUnavailable("secret path /models/x")
    monkeypatch.setattr("app.rag.retriever.get_reranker", broken)
    r = search(client, alice, "attendance", "hybrid_rerank")
    assert r.status_code == 503 and "secret" not in r.text
    assert search(client, alice, "attendance", "hybrid").status_code == 200  # other modes unaffected


def test_chat_accepts_rerank_mode(client, alice, corpus, reranker, monkeypatch):
    def grounded(system, user):
        sid = find_source(user, "15 March")
        return {"answer": f"15 March [{sid}]", "insufficient_evidence": False,
                "citations": [{"source_id": sid, "quote": "fee payment deadline is 15 March"}]}
    install_llm(monkeypatch, grounded)
    b = client.post("/api/chat", headers=alice, json={"message": "fee payment deadline", "mode": "hybrid_rerank"}).json()
    assert b["status"] == "answered" and b["retrieval_mode"] == "hybrid_rerank"


# ------------------------------------------------------------------ evaluation API

def benchmark_body(c):
    return {"name": "MLRITM test set", "items": [
        {"question": "attendance shortage condonation fee", "language": "en", "relevant": [{"document_id": c["reg"], "page": 2}]},
        {"question": "fee payment deadline", "language": "en", "relevant": [{"document_id": c["reg"], "page": 3}]},
        {"question": "Acme eligibility", "language": "en", "relevant": [{"document_id": c["plc"]}]},
        {"question": "weather on mars", "language": "en", "relevant": []}]}


def test_benchmark_run_matches_independent_ranking(client, alice, corpus, reranker):
    b = client.post("/api/evaluation/benchmarks", headers=alice, json=benchmark_body(corpus))
    assert b.status_code == 201 and b.json()["n_items"] == 4 and b.json()["n_scored"] == 3
    run = client.post("/api/evaluation/runs", headers=alice, json={
        "benchmark_id": b.json()["id"], "modes": ["vector", "bm25", "hybrid", "hybrid_rerank"], "top_k": 3})
    assert run.status_code == 201, run.text
    res = run.json()["results"]
    assert res["n_questions"] == 4 and res["n_scored"] == 3 and set(res["modes"]) == {"vector", "bm25", "hybrid", "hybrid_rerank"}
    for mode, data in res["modes"].items():
        o = data["overall"]
        assert o["n"] == 3 and all(0 <= o[k] <= 1 for k in ("precision@3", "recall@3", "mrr", "ndcg@3"))
        assert data["latency_ms"]["p95"] >= data["latency_ms"]["mean"] * 0 and len(data["items"]) == 3
        # independent cross-check: recompute each gold rank from the public search API
        gold = {"attendance shortage condonation fee": (corpus["reg"], 2), "fee payment deadline": (corpus["reg"], 3),
                "Acme eligibility": (corpus["plc"], None)}
        for item in data["items"]:
            doc, page = gold[item["question"]]
            hits = search(client, alice, item["question"], mode, top_k=3).json()["results"]
            rank = next((i for i, h in enumerate(hits, 1) if h["document_id"] == doc and (page is None or h["page_number"] == page)), None)
            assert item["first_relevant_rank"] == rank, (mode, item["question"])
            assert item["rr"] == (1 / rank if rank else 0)


def test_unavailable_reranker_only_marks_that_mode(client, alice, corpus, monkeypatch):
    def broken():
        raise RerankerUnavailable("x")
    monkeypatch.setattr("app.rag.retriever.get_reranker", broken)
    bid = client.post("/api/evaluation/benchmarks", headers=alice, json=benchmark_body(corpus)).json()["id"]
    res = client.post("/api/evaluation/runs", headers=alice, json={"benchmark_id": bid, "modes": ["vector", "hybrid_rerank"]}).json()["results"]
    assert res["modes"]["vector"]["overall"]["n"] == 3
    assert "error" in res["modes"]["hybrid_rerank"] and "overall" not in res["modes"]["hybrid_rerank"]


def test_run_listing_detail_and_analytics_summary(client, alice, corpus):
    assert client.get("/api/analytics/evaluation", headers=alice).json() == {"latest": None}
    bid = client.post("/api/evaluation/benchmarks", headers=alice, json=benchmark_body(corpus)).json()["id"]
    rid = client.post("/api/evaluation/runs", headers=alice, json={"benchmark_id": bid, "modes": ["vector", "hybrid"]}).json()["id"]
    listing = client.get("/api/evaluation/runs", headers=alice).json()
    assert len(listing) == 1 and "items" not in listing[0]["results"]["modes"]["vector"] and listing[0]["benchmark_name"] == "MLRITM test set"
    assert "items" in client.get(f"/api/evaluation/runs/{rid}", headers=alice).json()["results"]["modes"]["vector"]
    latest = client.get("/api/analytics/evaluation", headers=alice).json()["latest"]
    assert latest["run_id"] == rid and latest["n_scored"] == 3 and "items" not in latest["modes"]["hybrid"]
    assert client.delete(f"/api/evaluation/benchmarks/{bid}", headers=alice).status_code == 204
    assert client.get(f"/api/evaluation/runs/{rid}", headers=alice).status_code == 404  # cascaded


def test_evaluation_validation_and_ownership(client, alice, bob, corpus):
    good = benchmark_body(corpus)
    for bad in ({**good, "items": []}, {**good, "name": ""}, {**good, "items": [{"question": "", "relevant": []}]},
                {**good, "items": [{"question": "q", "language": "fr", "relevant": []}]},
                {**good, "items": [{"question": "q", "relevant": [{"document_id": corpus["reg"], "page": 0}]}]},
                {**good, "items": [{"question": "q"}] * 201}):
        assert client.post("/api/evaluation/benchmarks", headers=alice, json=bad).status_code == 422
    assert client.post("/api/evaluation/benchmarks", headers=bob, json=good).status_code == 404  # alice's documents
    bid = client.post("/api/evaluation/benchmarks", headers=alice, json=good).json()["id"]
    assert client.get(f"/api/evaluation/benchmarks/{bid}", headers=bob).status_code == 404
    assert client.post("/api/evaluation/runs", headers=bob, json={"benchmark_id": bid}).status_code == 404
    assert client.delete(f"/api/evaluation/benchmarks/{bid}", headers=bob).status_code == 404
    for body in ({"benchmark_id": bid, "modes": ["magic"]}, {"benchmark_id": bid, "top_k": 0}, {"benchmark_id": bid, "modes": []}):
        assert client.post("/api/evaluation/runs", headers=alice, json=body).status_code == 422
    unscored = client.post("/api/evaluation/benchmarks", headers=alice, json={"name": "n", "items": [{"question": "q"}]}).json()["id"]
    assert client.post("/api/evaluation/runs", headers=alice, json={"benchmark_id": unscored}).status_code == 422
    assert client.get("/api/evaluation/benchmarks").status_code == 401
    d = client.get(f"/api/evaluation/benchmarks/{bid}", headers=alice).json()
    assert d["items"][0]["relevant"][0]["page"] == 2 and d["items"][2]["relevant"][0]["page"] is None
