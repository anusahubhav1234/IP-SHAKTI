import re

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app.core.config import get_settings
from app.database.session import engine
from app.rag.llm import LLMError
from tests.fakes import ScriptedLLM, find_source, install_llm
from tests.helpers import make_pdf

A = b"Acme Corp placement drive. Eligibility: minimum 60 percent marks and no active backlogs. Registration is free."
B = b"Beta Ltd placement drive. Eligibility: minimum 70 percent marks and at most one backlog. Registration deadline is 20 March."
_SRC = re.compile(r'<<<SOURCE id="(S\d+)" doc="(D\d+)" document="([^"]*)"(?: page="(\d+)")?[^>]*>>>\n(.*?)\n<<<END SOURCE', re.S)


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
def admin(client, auth_headers):
    h = auth_headers("admin@example.com")
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET role='admin' WHERE email='admin@example.com'"))
    return h


@pytest.fixture
def two(client, alice):
    return {"a": up(client, alice, "acme.txt", A), "b": up(client, alice, "beta.txt", B)}


def src(user_prompt):
    return {sid: {"doc": d, "title": t, "text": body} for sid, d, t, _p, body in _SRC.findall(user_prompt)}


def sid_for(user_prompt, doc, needle):
    return next(sid for sid, s in src(user_prompt).items() if s["doc"] == doc and needle in s["text"])


def cmp_handler(**over):
    def h(system, user):
        a, b = sid_for(user, "D1", "Eligibility"), sid_for(user, "D2", "Eligibility")
        out = {"rows": [{"aspect": "Eligibility criteria", "cells": [
            {"doc": "D1", "value": "Minimum 60% and no active backlogs", "source_id": a,
             "quote": "minimum 60 percent marks and no active backlogs"},
            {"doc": "D2", "value": "Minimum 70% and at most one backlog", "source_id": b,
             "quote": "minimum 70 percent marks and at most one backlog"}]}],
            "similarities": [{"text": "Both require a minimum percentage.", "refs": [
                {"source_id": a, "quote": "minimum 60 percent marks"}, {"source_id": b, "quote": "minimum 70 percent marks"}]}],
            "differences": [{"text": "Acme needs 60% while Beta needs 70%.", "refs": [
                {"source_id": a, "quote": "minimum 60 percent marks"}, {"source_id": b, "quote": "minimum 70 percent marks"}]}]}
        out.update(over(a, b) if callable(over.get("fn")) else {})
        return out
    return h


def compare(client, headers, ids, **kw):
    return client.post("/api/documents/compare", headers=headers, json={"document_ids": ids, "aspects": ["Eligibility criteria"], **kw})


# ------------------------------------------------------------------ comparison

def test_comparison_table_with_verified_citations(client, alice, two, monkeypatch):
    llm = install_llm(monkeypatch, cmp_handler())
    r = compare(client, alice, [two["a"], two["b"]])
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "ok" and [d["label"] for d in b["documents"]] == ["D1", "D2"]
    (row,) = b["rows"]
    assert row["aspect"] == "Eligibility criteria" and len(row["cells"]) == 2
    for cell, doc, title in zip(row["cells"], (two["a"], two["b"]), ("acme", "beta")):
        assert cell["found"] and cell["verified"] and cell["document_id"] == doc
        assert cell["citation"]["document_id"] == doc and cell["citation"]["document_title"] == title
    assert row["cells"][0]["citation"]["excerpt"] == "minimum 60 percent marks and no active backlogs"
    assert all(c["verified"] for c in b["similarities"] + b["differences"]) and len(b["differences"][0]["citations"]) == 2
    system, user = llm.calls[0]
    assert "untrusted" in system.lower() and "VERBATIM" in system and 'doc="D1"' in user and 'doc="D2"' in user


def test_cell_citing_the_wrong_document_or_a_fake_quote_is_unverified(client, alice, two, monkeypatch):
    def liar(system, user):
        a, b = sid_for(user, "D1", "Eligibility"), sid_for(user, "D2", "Eligibility")
        return {"rows": [{"aspect": "Eligibility criteria", "cells": [
            {"doc": "D1", "value": "needs 90%", "source_id": a, "quote": "needs ninety percent marks always"},   # fabricated quote
            {"doc": "D2", "value": "needs 70%", "source_id": a, "quote": "minimum 60 percent marks and no active"}]}],  # D1's source for D2
            "similarities": [{"text": "no refs claim", "refs": []}],
            "differences": [{"text": "half-true", "refs": [{"source_id": a, "quote": "minimum 60 percent marks"},
                                                            {"source_id": b, "quote": "totally invented quote text"}]}]}
    install_llm(monkeypatch, liar)
    b = compare(client, alice, [two["a"], two["b"]]).json()
    c1, c2 = b["rows"][0]["cells"]
    assert c1["found"] and not c1["verified"] and c1["citation"] is not None and c1["citation"]["verified"] is False
    assert c2["found"] and not c2["verified"] and c2["citation"] is None      # cross-document citation is dropped
    assert b["similarities"][0]["verified"] is False and b["differences"][0]["verified"] is False


def test_missing_information_is_reported_not_invented(client, alice, two, monkeypatch):
    def partial(system, user):
        a = sid_for(user, "D1", "Eligibility")
        return {"rows": [{"aspect": "Eligibility criteria", "cells": [
            {"doc": "D1", "value": "ok", "source_id": a, "quote": "minimum 60 percent marks and no active backlogs"},
            {"doc": "D2", "value": "", "source_id": "", "quote": ""}]}], "similarities": [], "differences": []}
    install_llm(monkeypatch, partial)
    cells = compare(client, alice, [two["a"], two["b"]]).json()["rows"][0]["cells"]
    assert cells[1]["found"] is False and cells[1]["value"] == "" and cells[1]["citation"] is None


def test_default_aspects_and_language(client, alice, two, monkeypatch):
    llm = install_llm(monkeypatch, lambda s, u: {"rows": [], "similarities": [], "differences": []})
    b = client.post("/api/documents/compare", headers=alice, json={"document_ids": [two["a"], two["b"]], "language": "te"}).json()
    assert [r["aspect"] for r in b["rows"]] == ["Eligibility criteria", "Important dates and deadlines", "Fees",
                                                 "Rules and regulations", "Requirements and required documents"]
    assert all(not c["found"] for r in b["rows"] for c in r["cells"]) and b["language"] == "te"
    assert "Telugu" in llm.calls[0][0]


def test_comparison_without_evidence_skips_llm(client, alice, two, monkeypatch):
    llm = install_llm(monkeypatch, cmp_handler())
    monkeypatch.setattr("app.services.comparison.retrieve", lambda *a, **k: type("R", (), {"hits": []})())
    b = compare(client, alice, [two["a"], two["b"]]).json()
    assert b["status"] == "insufficient_evidence" and b["rows"] == [] and llm.calls == []


def test_comparison_validation_ownership_and_errors(client, alice, bob, two, monkeypatch):
    install_llm(monkeypatch, cmp_handler())
    assert compare(client, alice, [two["a"]]).status_code == 422
    assert compare(client, alice, [two["a"], two["a"]]).status_code == 422
    assert compare(client, alice, [two["a"], two["b"]] * 3).status_code == 422
    assert client.post("/api/documents/compare", headers=alice, json={"document_ids": [two["a"], two["b"]], "aspects": []}).status_code == 422
    assert compare(client, bob, [two["a"], two["b"]]).status_code == 404
    with engine.begin() as conn:
        conn.execute(text("UPDATE documents SET status='failed' WHERE title='beta'"))
    assert compare(client, alice, [two["a"], two["b"]]).status_code == 404
    assert client.post("/api/documents/compare", json={"document_ids": [two["a"], two["b"]]}).status_code == 401
    with engine.begin() as conn:
        conn.execute(text("UPDATE documents SET status='ready'"))
    install_llm(monkeypatch, lambda s, u: (_ for _ in ()).throw(LLMError("rate_limited", "busy")))
    assert compare(client, alice, [two["a"], two["b"]]).status_code == 429
    install_llm(monkeypatch, lambda s, u: "no json here")
    assert compare(client, alice, [two["a"], two["b"]]).status_code == 502


# ------------------------------------------------------------------ analytics

def test_user_overview_is_real_and_private(client, alice, bob, monkeypatch):
    empty = client.get("/api/analytics/overview", headers=alice).json()
    assert empty["documents"]["total"] == 0 and empty["chunks"] == 0 and empty["conversations"] == 0
    assert empty["language_usage"] == {} and empty["latency_ms"]["avg"] is None and len(empty["activity"]) == 14
    assert all(d["search"] == 0 and d["chat"] == 0 for d in empty["activity"])

    reg = up(client, alice, "regulations.pdf", make_pdf(["Fee schedule. The fee payment deadline is 15 March."]))
    up(client, alice, "broken.pdf", b"%PDF-1.4 garbage")
    def grounded(system, user):
        sid = find_source(user, "15 March")
        return {"answer": f"15 March [{sid}]", "insufficient_evidence": False,
                "citations": [{"source_id": sid, "quote": "fee payment deadline is 15 March"}]}
    install_llm(monkeypatch, grounded)
    chat = client.post("/api/chat", headers=alice, json={"message": "fee payment deadline?"}).json()
    client.post("/api/chat", headers=alice, json={"message": "పరీక్ష ఫీజు గడువు ఎప్పుడు?", "mode": "bm25"})  # no keyword hit -> no evidence
    client.post("/api/search", headers=alice, json={"query": "fee"})
    client.post(f"/api/messages/{chat['message_id']}/feedback", headers=alice, json={"rating": 1})
    o = client.get("/api/analytics/overview", headers=alice).json()
    assert o["documents"] == {"total": 2, "by_status": {"pending": 0, "processing": 0, "ready": 1, "failed": 1}}
    assert o["chunks"] >= 1 and o["conversations"] == 2 and o["messages"] == {"user": 2, "assistant": 2, "insufficient_evidence": 1}
    assert o["language_usage"] == {"en": 1, "te": 1} and o["feedback"] == {"up": 1, "down": 0}
    assert o["retrieval_modes"] == {"hybrid": 1, "bm25": 1} and o["latency_ms"]["avg"] is not None
    today = o["activity"][-1]
    assert today["chat"] == 2 and today["search"] == 1
    b = client.get("/api/analytics/overview", headers=bob).json()
    assert b["documents"]["total"] == 0 and b["conversations"] == 0 and b["language_usage"] == {} and b["activity"][-1]["chat"] == 0
    assert client.get("/api/analytics/overview").status_code == 401


# ------------------------------------------------------------------ admin

ADMIN_GETS = ["/api/admin/overview", "/api/admin/users", "/api/admin/documents", "/api/admin/system-health"]


def test_admin_endpoints_require_admin(client, alice):
    for url in ADMIN_GETS:
        assert client.get(url).status_code == 401, url
        assert client.get(url, headers=alice).status_code == 403, url
    uid = client.get("/api/auth/me", headers=alice).json()["id"]
    assert client.patch(f"/api/admin/users/{uid}", headers=alice, json={"is_active": False}).status_code == 403


def test_admin_user_management(client, admin, alice, bob):
    users = client.get("/api/admin/users", headers=admin).json()
    assert users["total"] == 3 and {u["email"] for u in users["items"]} == {"admin@example.com", "alice@example.com", "bob@example.com"}
    assert "password_hash" not in str(users)
    assert client.get("/api/admin/users", headers=admin, params={"q": "ali"}).json()["total"] == 1
    assert client.get("/api/admin/users", headers=admin, params={"q": "%"}).json()["total"] == 0
    up(client, alice, "n.txt", b"alice private text file")
    row = next(u for u in client.get("/api/admin/users", headers=admin).json()["items"] if u["email"] == "alice@example.com")
    assert row["document_count"] == 1 and row["role"] == "user"
    uid = row["id"]

    r = client.patch(f"/api/admin/users/{uid}", headers=admin, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.get("/api/auth/me", headers=alice).status_code == 401                       # existing token dies immediately
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "Password123"}).status_code == 401
    assert client.patch(f"/api/admin/users/{uid}", headers=admin, json={"is_active": True, "role": "admin"}).json()["role"] == "admin"
    assert client.get("/api/admin/users", headers=alice).status_code == 200                    # promoted, same password works again

    me = client.get("/api/auth/me", headers=admin).json()["id"]
    assert client.patch(f"/api/admin/users/{me}", headers=admin, json={"role": "user"}).status_code == 400
    assert client.patch("/api/admin/users/00000000-0000-0000-0000-000000000001", headers=admin, json={}).status_code == 404
    assert client.patch(f"/api/admin/users/{uid}", headers=admin, json={"role": "root"}).status_code == 422
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM audit_logs WHERE action='admin.user_update'")).scalar_one()
    assert n == 2


def test_admin_documents_overview_and_cross_user_delete(client, admin, alice):
    good = up(client, alice, "ok.txt", b"some readable text for the knowledge base")
    up(client, alice, "bad.pdf", b"%PDF-1.4 not a pdf")
    docs = client.get("/api/admin/documents", headers=admin).json()
    assert docs["total"] == 2 and {d["owner_email"] for d in docs["items"]} == {"alice@example.com"}
    assert next(d for d in docs["items"] if d["id"] == good)["chunk_count"] >= 1
    assert client.get("/api/admin/documents", headers=admin, params={"status": "failed"}).json()["total"] == 1
    assert client.get("/api/admin/documents", headers=admin, params={"q": "alice"}).json()["total"] == 2
    assert client.get("/api/admin/documents", headers=admin, params={"status": "nope"}).status_code == 422
    ov = client.get("/api/admin/overview", headers=admin).json()
    assert ov["users"] == {"total": 2, "active": 2} and ov["documents"]["by_status"]["failed"] == 1
    assert ov["processing_failures"][0]["filename"] == "bad.pdf" and "PDF" in ov["processing_failures"][0]["error"]
    assert client.delete(f"/api/documents/{good}", headers=admin).status_code == 204
    assert client.get("/api/admin/documents", headers=admin).json()["total"] == 1


def test_system_health_reports_real_checks_and_hides_secrets(client, admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("SECRET-KEY-VALUE"))
    r = client.get("/api/admin/system-health", headers=admin)
    h = r.json()
    assert h["status"] == "healthy" and h["checks"]["database"]["ok"] and h["checks"]["pgvector"]["ok"] and h["checks"]["storage"]["ok"]
    assert h["checks"]["llm"]["ok"] is True and "SECRET" not in r.text and h["checks"]["embeddings"]["dim"] == 384
    assert set(h["checks"]["ocr"]["languages"]) <= {"eng", "hin", "tel"} and h["chunks_without_embedding"] == 0
    monkeypatch.setattr(get_settings(), "gemini_api_key", None)
    assert client.get("/api/admin/system-health", headers=admin).json()["checks"]["llm"]["ok"] is False
