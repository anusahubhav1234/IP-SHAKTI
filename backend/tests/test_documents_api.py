import os
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.database.session import engine
from tests.helpers import make_docx, make_pdf
from tests.test_text_pipeline import TELUGU

PDF_PAGES = ["Page one covers attendance. Students need 75 percent attendance for examinations.",
             "Page two covers fees. The fee payment deadline is 15 March.",
             "Page three covers scholarships and required documents."]


def upload(client, headers, name="rules.pdf", data=None, **form):
    data = make_pdf(PDF_PAGES) if data is None else data
    return client.post("/api/documents/upload", headers=headers, files={"file": (name, data)}, data=form)


@pytest.fixture
def alice(auth_headers):
    return auth_headers("alice@example.com")


@pytest.fixture
def bob(client, make_user):
    make_user(email="bob@example.com")
    r = client.post("/api/auth/login", json={"email": "bob@example.com", "password": "Password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_upload_pdf_processes_to_ready_with_page_accurate_chunks(client, alice):
    r = upload(client, alice, title="Regulations")
    assert r.status_code == 202, r.text
    doc_id = r.json()["id"]
    st = client.get(f"/api/documents/{doc_id}/status", headers=alice).json()
    assert st["status"] == "ready" and st["stage"] == "done" and st["chunk_count"] >= 3 and st["error"] is None
    doc = client.get(f"/api/documents/{doc_id}", headers=alice).json()
    assert doc["title"] == "Regulations" and doc["page_count"] == 3 and doc["language"] == "en"
    for page, needle in ((1, "attendance"), (2, "15 March"), (3, "scholarships")):
        chunks = client.get(f"/api/documents/{doc_id}/chunks", params={"page": page}, headers=alice).json()["items"]
        assert chunks and all(c["page_number"] == page for c in chunks)
        assert any(needle in c["text"] for c in chunks)


def test_embeddings_stored_as_384_dim_vectors_and_searchable(client, alice):
    upload(client, alice)
    with engine.connect() as conn:
        dims = conn.execute(text("SELECT DISTINCT vector_dims(embedding) FROM document_chunks")).scalars().all()
        assert dims == [384]
        from tests.fakes import FakeEmbedder
        q = FakeEmbedder().embed_query("fee payment deadline")
        top = conn.execute(text("SELECT page_number FROM document_chunks ORDER BY embedding <=> CAST(:q AS vector) LIMIT 1"),
                           {"q": str(q)}).scalar_one()
    assert top == 2  # pgvector cosine search returns the page about fees


def test_upload_docx_txt_csv_faq(client, alice):
    d = upload(client, alice, "a.docx", make_docx()).json()
    t = upload(client, alice, "t.txt", TELUGU.encode()).json()
    c = upload(client, alice, "c.csv", b"Company,Eligibility\nA,60%\nB,70%\n").json()
    f = upload(client, alice, "faq.csv", b"Question,Answer\nFee deadline?,15 March\n", as_faq="true").json()
    for doc, typ in ((d, "docx"), (t, "txt"), (c, "csv"), (f, "faq")):
        st = client.get(f"/api/documents/{doc['id']}/status", headers=alice).json()
        assert st["status"] == "ready", (typ, st)
        assert doc["source_type"] == typ
    assert client.get(f"/api/documents/{t['id']}", headers=alice).json()["language"] == "te"
    faq_chunks = client.get(f"/api/documents/{f['id']}/chunks", headers=alice).json()["items"]
    assert faq_chunks[0]["section_heading"] == "FAQ row 2" and faq_chunks[0]["page_number"] is None


def test_validation_rejections(client, alice, monkeypatch):
    assert upload(client, alice, "x.exe", b"MZ....").status_code == 415
    assert upload(client, alice, "fake.pdf", b"just some text").status_code == 400
    assert upload(client, alice, "fake.docx", b"PK\x03\x04notreallyazip").status_code == 400
    assert upload(client, alice, "bin.txt", b"abc\x00\x01\x02def").status_code == 400
    assert upload(client, alice, "empty.pdf", b"").status_code == 400
    assert upload(client, alice, "n.txt", b"hello", as_faq="true").status_code == 400
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    assert upload(client, alice, "big.txt", b"a" * (1024 * 1024 + 10)).status_code == 413
    assert client.post("/api/documents/upload", files={"file": ("a.txt", b"hi")}).status_code == 401


def test_malicious_filename_cannot_escape_storage(client, alice):
    r = upload(client, alice, "../../../etc/evil.txt", b"harmless text content")
    assert r.status_code == 202 and r.json()["filename"] == "evil.txt"
    with engine.connect() as conn:
        path = conn.execute(text("SELECT storage_path FROM documents")).scalar_one()
    assert Path(path).resolve().is_relative_to(Path(os.environ["STORAGE_DIR"]).resolve())
    assert "evil" not in path


def test_duplicate_upload_rejected_but_allowed_for_other_user(client, alice, bob):
    same = make_pdf(PDF_PAGES)  # make_pdf embeds a timestamp, so reuse one byte string
    assert upload(client, alice, data=same).status_code == 202
    dup = upload(client, alice, "renamed.pdf", same)
    assert dup.status_code == 409 and "already uploaded" in dup.json()["detail"]
    assert upload(client, bob, data=same).status_code == 202


def test_corrupt_pdf_marked_failed_with_safe_error(client, alice):
    r = upload(client, alice, "broken.pdf", b"%PDF-1.4\nthis is not a real pdf body")
    assert r.status_code == 202
    st = client.get(f"/api/documents/{r.json()['id']}/status", headers=alice).json()
    assert st["status"] == "failed" and "PDF" in st["error"] and "Traceback" not in st["error"]
    assert st["chunk_count"] == 0


def test_unexpected_pipeline_error_hides_internals(client, alice, monkeypatch):
    from app.rag import embeddings

    def boom():
        raise RuntimeError("secret internal path /srv/models/x")
    monkeypatch.setattr(embeddings, "get_embedder", boom)
    r = upload(client, alice)
    st = client.get(f"/api/documents/{r.json()['id']}/status", headers=alice).json()
    assert st["status"] == "failed" and "secret" not in st["error"]


def test_access_control_between_users(client, alice, bob):
    doc_id = upload(client, alice).json()["id"]
    for method, url in (("get", f"/api/documents/{doc_id}"), ("get", f"/api/documents/{doc_id}/status"),
                        ("get", f"/api/documents/{doc_id}/chunks"), ("get", f"/api/documents/{doc_id}/file"),
                        ("post", f"/api/documents/{doc_id}/reprocess"), ("delete", f"/api/documents/{doc_id}")):
        assert getattr(client, method)(url, headers=bob).status_code == 404, url
        assert getattr(client, method)(url).status_code == 401, url
    assert client.get("/api/documents", headers=bob).json() == {"items": [], "total": 0}
    assert client.get(f"/api/documents/{doc_id}", headers=alice).status_code == 200


def test_admin_can_access_any_document(client, alice, auth_headers):
    doc_id = upload(client, alice).json()["id"]
    admin = auth_headers("admin@example.com")
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET role='admin' WHERE email='admin@example.com'"))
    assert client.get(f"/api/documents/{doc_id}", headers=admin).status_code == 200
    assert client.get("/api/documents", headers=admin).json()["total"] == 0  # list is still own-only


def test_list_search_filter_pagination(client, alice):
    upload(client, alice, "attendance_policy.pdf", make_pdf(["attendance policy text"]), title="Attendance Policy")
    upload(client, alice, "fees.txt", b"fee structure text", title="Fee Structure")
    upload(client, alice, "broken.pdf", b"%PDF-1.4 garbage")
    all_ = client.get("/api/documents", headers=alice).json()
    assert all_["total"] == 3
    assert client.get("/api/documents", params={"q": "attend"}, headers=alice).json()["total"] == 1
    assert client.get("/api/documents", params={"q": "%"}, headers=alice).json()["total"] == 0  # wildcard escaped
    assert client.get("/api/documents", params={"status": "failed"}, headers=alice).json()["total"] == 1
    assert client.get("/api/documents", params={"status": "bogus"}, headers=alice).status_code == 422
    page = client.get("/api/documents", params={"limit": 2, "offset": 2}, headers=alice).json()
    assert len(page["items"]) == 1 and page["total"] == 3


def test_categories_and_ownership(client, alice, bob):
    cat = client.post("/api/categories", json={"name": "Regulations"}, headers=alice)
    assert cat.status_code == 201
    cid = cat.json()["id"]
    assert client.post("/api/categories", json={"name": "regulations"}, headers=alice).status_code == 409
    assert client.post("/api/categories", json={"name": "   "}, headers=alice).status_code == 422
    assert client.get("/api/categories", headers=bob).json() == []
    assert upload(client, bob, category_id=cid).status_code == 404  # cannot file under someone else's category
    doc = upload(client, alice, category_id=cid).json()
    assert client.get("/api/documents", params={"category_id": cid}, headers=alice).json()["total"] == 1
    assert client.delete(f"/api/categories/{cid}", headers=bob).status_code == 404
    assert client.delete(f"/api/categories/{cid}", headers=alice).status_code == 204
    assert client.get(f"/api/documents/{doc['id']}", headers=alice).json()["category_id"] is None


def test_file_download_is_inline_for_pdf_with_nosniff(client, alice):
    doc_id = upload(client, alice).json()["id"]
    r = client.get(f"/api/documents/{doc_id}/file", headers=alice)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert r.headers["content-disposition"].startswith("inline") and r.headers["x-content-type-options"] == "nosniff"
    t = upload(client, alice, "n.txt", b"plain text file").json()["id"]
    assert client.get(f"/api/documents/{t}/file", headers=alice).headers["content-disposition"].startswith("attachment")


def test_reprocess_is_idempotent_and_recovers_failed_docs(client, alice):
    doc_id = upload(client, alice).json()["id"]
    before = client.get(f"/api/documents/{doc_id}/status", headers=alice).json()["chunk_count"]
    r = client.post(f"/api/documents/{doc_id}/reprocess", headers=alice)
    assert r.status_code == 202
    st = client.get(f"/api/documents/{doc_id}/status", headers=alice).json()
    assert st["status"] == "ready" and st["chunk_count"] == before  # no duplicated chunks
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM processing_jobs")).scalar_one() == 2


def test_delete_removes_file_chunks_jobs_and_audits(client, alice):
    doc_id = upload(client, alice).json()["id"]
    with engine.connect() as conn:
        path = conn.execute(text("SELECT storage_path FROM documents")).scalar_one()
    assert Path(path).exists()
    assert client.delete(f"/api/documents/{doc_id}", headers=alice).status_code == 204
    assert not Path(path).exists()
    with engine.connect() as conn:
        for tbl in ("documents", "document_chunks", "processing_jobs"):
            assert conn.execute(text(f"SELECT count(*) FROM {tbl}")).scalar_one() == 0
        actions = conn.execute(text("SELECT action FROM audit_logs WHERE action LIKE 'document.%' ORDER BY id")).scalars().all()
    assert actions == ["document.upload", "document.delete"]
    assert client.get(f"/api/documents/{doc_id}", headers=alice).status_code == 404


def test_deleting_user_cascades_documents(client, alice):
    upload(client, alice)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email='alice@example.com'"))
        assert conn.execute(text("SELECT count(*) FROM document_chunks")).scalar_one() == 0
