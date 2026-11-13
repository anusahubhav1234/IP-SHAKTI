import pytest
from sqlalchemy import text

from app.database.session import SessionLocal, engine
from app.rag import bm25 as bm25_mod
from tests.helpers import make_pdf
from tests.test_text_pipeline import TELUGU

REG_PAGES = ["Attendance rules. Students must maintain 75 percent attendance to appear for examinations.",
             "Fee schedule. The fee payment deadline is 15 March for all semesters.",
             "Scholarship guidelines. Required documents include income certificate and marksheet."]
PLACEMENT = "Acme Corp placement drive. Eligibility: minimum 60 percent marks and no active backlogs."


def up(client, headers, name, data):
    r = client.post("/api/documents/upload", headers=headers, files={"file": (name, data)})
    assert r.status_code == 202, r.text
    return r.json()["id"]


@pytest.fixture
def alice(auth_headers):
    return auth_headers("alice@example.com")


@pytest.fixture
def bob(client, make_user):
    make_user(email="bob@example.com")
    r = client.post("/api/auth/login", json={"email": "bob@example.com", "password": "Password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def corpus(client, alice):
    reg = up(client, alice, "regulations.pdf", make_pdf(REG_PAGES))
    plc = up(client, alice, "placement.txt", PLACEMENT.encode())
    return {"reg": reg, "plc": plc}


def search(client, headers, query, mode="vector", **kw):
    return client.post("/api/search", headers=headers, json={"query": query, "mode": mode, **kw})


def test_vector_mode_finds_the_right_page(client, alice, corpus):
    r = search(client, alice, "fee payment deadline", "vector", top_k=3)
    assert r.status_code == 200
    body = r.json()
    top = body["results"][0]
    assert top["document_title"] == "regulations" and top["page_number"] == 2 and "15 March" in top["text"]
    assert body["mode"] == "vector" and body["detected_language"] == "en"
    assert all(h["bm25_rank"] is None for h in body["results"])
    scores = [h["score"] for h in body["results"]]
    assert scores == sorted(scores, reverse=True) and all(-1.0 <= s <= 1.0 for s in scores)
    assert {"embed_query", "vector_search", "total"} <= set(body["timings_ms"])


def test_bm25_mode_exact_keyword_and_only_positive_scores(client, alice, corpus):
    r = search(client, alice, "Acme", "bm25").json()
    assert len(r["results"]) == 1 and r["results"][0]["document_title"] == "placement"
    h = r["results"][0]
    assert h["bm25_rank"] == 1 and h["bm25_score"] > 0 and h["vector_rank"] is None
    assert search(client, alice, "zzzunknownterm", "bm25").json()["results"] == []


def test_hybrid_endpoint_fuses_and_keeps_component_ranks(client, alice, corpus):
    r = client.post("/api/search/hybrid", headers=alice, json={"query": "fee payment deadline", "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "hybrid" and "fusion" in body["timings_ms"]
    top = body["results"][0]
    assert top["page_number"] == 2 and top["vector_rank"] is not None and top["bm25_rank"] is not None
    expected = 1 / (60 + top["vector_rank"]) + 1 / (60 + top["bm25_rank"])
    assert abs(top["score"] - expected) < 1e-9


def test_hybrid_recovers_keyword_hit_that_vector_search_misses(client, alice, corpus, monkeypatch):
    """Mechanism check: when the semantic retriever misses an exact-keyword passage, fusion still surfaces it."""
    from app.rag import retriever
    real = retriever.vector_search

    def vector_without_acme(db, user_id, qvec, k, doc_ids=None):
        return [h for h in real(db, user_id, qvec, k, doc_ids) if h.document_title != "placement"]
    monkeypatch.setattr(retriever, "vector_search", vector_without_acme)
    vec = search(client, alice, "Acme eligibility", "vector", top_k=5).json()["results"]
    hyb = client.post("/api/search/hybrid", headers=alice, json={"query": "Acme eligibility", "top_k": 5}).json()["results"]
    assert all(h["document_title"] != "placement" for h in vec)
    # (RRF ties single-list rank-1 hits, so check presence rather than position)
    plc = [h for h in hyb if h["document_title"] == "placement"]
    assert plc and plc[0]["vector_rank"] is None and plc[0]["bm25_rank"] == 1


def test_top_k_and_document_filter(client, alice, corpus):
    assert len(search(client, alice, "attendance", top_k=2).json()["results"]) == 2
    only_plc = search(client, alice, "percent", "hybrid", document_ids=[corpus["plc"]]).json()["results"]
    assert only_plc and all(h["document_id"] == corpus["plc"] for h in only_plc)
    only_plc_bm = search(client, alice, "percent", "bm25", document_ids=[corpus["plc"]]).json()["results"]
    assert only_plc_bm and all(h["document_id"] == corpus["plc"] for h in only_plc_bm)


def test_users_cannot_search_each_others_documents(client, alice, bob, corpus):
    for mode in ("vector", "bm25", "hybrid"):
        assert search(client, bob, "Acme eligibility attendance", mode).json()["results"] == []
    bob_doc = up(client, bob, "bob.txt", b"Bob private notes about hostel allotment")
    r = search(client, bob, "hostel", "hybrid").json()["results"]
    assert [h["document_id"] for h in r] == [bob_doc]
    # alice's search never returns bob's document (vector search always returns *her* nearest chunks)
    assert all(h["document_id"] != bob_doc for h in search(client, alice, "hostel", "hybrid").json()["results"])
    assert search(client, alice, "hostel", "bm25").json()["results"] == []
    # cannot target someone else's document id
    assert search(client, bob, "Acme", document_ids=[corpus["plc"]]).status_code == 404


def test_only_ready_documents_are_searchable(client, alice, corpus):
    assert search(client, alice, "Acme", "bm25").json()["results"]
    with engine.begin() as conn:
        conn.execute(text("UPDATE documents SET status='failed' WHERE title='placement'"))
    assert search(client, alice, "Acme", "bm25").json()["results"] == []
    assert all(h["document_title"] != "placement" for h in search(client, alice, "Acme", "vector").json()["results"])
    assert search(client, alice, "Acme", document_ids=[corpus["plc"]]).status_code == 404


def test_bm25_index_is_cached_and_refreshes_on_change(client, alice, corpus, monkeypatch):
    builds = []
    real = bm25_mod._build
    monkeypatch.setattr(bm25_mod, "_build", lambda *a, **k: (builds.append(1), real(*a, **k))[1])
    search(client, alice, "attendance", "bm25")
    search(client, alice, "fee", "bm25")
    assert len(builds) == 1  # second query reused the index
    assert search(client, alice, "hostel", "bm25").json()["results"] == []
    new = up(client, alice, "hostel.txt", b"Hostel allotment rules for first year students")
    assert [h["document_id"] for h in search(client, alice, "hostel", "bm25").json()["results"]] == [new]
    assert len(builds) == 2  # rebuilt after upload
    client.delete(f"/api/documents/{new}", headers=alice)
    assert search(client, alice, "hostel", "bm25").json()["results"] == []


def test_telugu_query_and_document(client, alice):
    tid = up(client, alice, "telugu.txt", TELUGU.encode())
    up(client, alice, "english.txt", b"Library timings are 9 am to 5 pm on weekdays")
    for mode in ("bm25", "hybrid"):
        r = search(client, alice, "హాజరు శాతం", mode).json()
        assert r["detected_language"] == "te"
        assert r["results"][0]["document_id"] == tid


def test_validation_and_auth(client, alice, corpus):
    for body in ({"query": ""}, {"query": "   "}, {"query": "x" * 1001}, {"query": "a", "top_k": 0},
                 {"query": "a", "top_k": 21}, {"query": "a", "mode": "magic"}, {"query": "a", "mode": "rerank"},
                 {"query": "a", "document_ids": ["not-a-uuid"]}):
        assert client.post("/api/search", headers=alice, json=body).status_code == 422, body
    assert client.post("/api/search", json={"query": "a"}).status_code == 401
    assert client.post("/api/search/hybrid", json={"query": "a"}).status_code == 401


def test_search_is_audited_without_storing_the_query(client, alice, corpus):
    search(client, alice, "my secret question about fees", "hybrid")
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT details::text FROM audit_logs WHERE action='search'")).scalars().all()
    assert len(rows) == 1 and '"mode": "hybrid"' in rows[0] and '"language": "en"' in rows[0]
    assert "secret" not in rows[0]


def test_vector_search_exact_scan_fallback_when_index_returns_too_few(client, alice, corpus, monkeypatch):
    """HNSW + WHERE can under-return. Simulate that and check the exact-scan fallback restores k results."""
    from app.models import User
    from app.rag import vector
    from sqlalchemy import select
    from tests.fakes import FakeEmbedder
    calls = []
    real = vector._query

    def short_first(*a, **k):
        calls.append(1)
        stmt = real(*a, **k)
        return stmt.limit(1) if len(calls) == 1 else stmt
    monkeypatch.setattr(vector, "_query", short_first)
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.email == "alice@example.com"))
        hits = vector.vector_search(db, uid, FakeEmbedder().embed_query("attendance"), 4)
    assert len(calls) == 2 and len(hits) == 4


def test_bm25_works_on_tiny_corpora(client, alice):
    """Regression: default rank_bm25 IDF is <= 0 on 1-2 chunk corpora, which returned no keyword hits."""
    up(client, alice, "one.txt", b"Hostel allotment rules for first year students")
    r = search(client, alice, "hostel allotment", "bm25").json()["results"]
    assert len(r) == 1 and r[0]["bm25_score"] > 0
    up(client, alice, "two.txt", b"Hostel fees are payable every semester")
    both = search(client, alice, "hostel", "bm25").json()["results"]  # term in 100% of chunks
    assert len(both) == 2 and all(h["bm25_score"] > 0 for h in both)
