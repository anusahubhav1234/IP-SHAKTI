import os

# Must be set before the app (and its cached settings) is imported.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://sakti:sakti@localhost:5432/sakti_test")
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-0123"
os.environ["RATE_LIMIT_ENABLED"] = "false"
import tempfile
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="sakti_test_storage_")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database.session import engine


def _alembic_cfg() -> Config:
    return Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))


@pytest.fixture(scope="session", autouse=True)
def _migrated_db():
    """Builds the schema through the real Alembic migrations, not metadata.create_all."""
    assert "sakti_test" in str(engine.url), "Refusing to run tests against a non-test database"
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(_alembic_cfg(), "head")
    yield


@pytest.fixture(autouse=True)
def _clean_tables(_migrated_db):
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users, audit_logs, document_categories RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch):
    from app.rag import embeddings
    from tests.fakes import FakeEmbedder
    monkeypatch.setattr(embeddings, "get_embedder", lambda: FakeEmbedder())


@pytest.fixture(autouse=True)
def _clear_bm25_cache():
    from app.rag import bm25
    bm25.clear_cache()
    yield
    bm25.clear_cache()


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_user(client):
    def _make(email="student@example.com", password="Password123", name="Test Student"):
        r = client.post("/api/auth/register", json={"email": email, "password": password, "full_name": name})
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture
def auth_headers(client, make_user):
    def _headers(email="student@example.com", password="Password123"):
        make_user(email=email, password=password)
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _headers
