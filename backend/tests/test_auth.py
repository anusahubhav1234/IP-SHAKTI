import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import require_admin
from app.core.config import get_settings
from app.database.session import SessionLocal, engine


def test_register_creates_normal_user(client):
    r = client.post("/api/auth/register",
                    json={"email": "A@Example.com", "password": "Password123", "full_name": "Asha"})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "a@example.com"  # normalised
    assert body["role"] == "user"
    assert "password" not in body and "password_hash" not in body


def test_register_cannot_choose_role(client):
    r = client.post("/api/auth/register", json={"email": "x@example.com", "password": "Password123",
                                                "full_name": "Mallory", "role": "admin"})
    assert r.status_code == 201
    assert r.json()["role"] == "user"


def test_password_is_hashed_not_plaintext(client, make_user):
    make_user(password="Password123")
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT password_hash FROM users")).scalar_one()
    assert stored != "Password123" and stored.startswith("$2")


def test_duplicate_email_rejected(client, make_user):
    make_user()
    r = client.post("/api/auth/register", json={"email": "STUDENT@example.com",
                                                "password": "Password123", "full_name": "Dup"})
    assert r.status_code == 409


def test_weak_or_invalid_input_rejected(client):
    base = {"email": "ok@example.com", "full_name": "Okay Name", "password": "Password123"}
    for patch in ({"password": "short1"}, {"password": "alllettersnodigit"}, {"password": "12345678"},
                  {"password": "a1" * 40}, {"email": "not-an-email"}, {"full_name": "A"}):
        r = client.post("/api/auth/register", json={**base, **patch})
        assert r.status_code == 422, patch


def test_login_success_and_me(client, make_user):
    make_user()
    r = client.post("/api/auth/login", json={"email": "student@example.com", "password": "Password123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "student@example.com"


def test_login_failures_are_generic(client, make_user):
    make_user()
    wrong_pw = client.post("/api/auth/login", json={"email": "student@example.com", "password": "Wrong12345"})
    no_user = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Password123"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_protected_route_requires_valid_token(client, auth_headers):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    good = auth_headers()["Authorization"].split()[1]
    tampered = good[:-3] + ("AAA" if not good.endswith("AAA") else "BBB")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


def test_expired_and_foreign_tokens_rejected(client, make_user):
    user = make_user()
    s = get_settings()
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode({"sub": user["id"], "exp": past}, s.jwt_secret, algorithm=s.jwt_algorithm)
    wrong_key = jwt.encode({"sub": user["id"], "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                           "some-other-secret-value", algorithm="HS256")
    unknown_user = jwt.encode({"sub": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                              s.jwt_secret, algorithm=s.jwt_algorithm)
    for tok in (expired, wrong_key, unknown_user):
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_inactive_user_cannot_use_token(client, auth_headers):
    headers = auth_headers()
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET is_active = false"))
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_admin_role_enforced_from_database_not_token(client, auth_headers):
    app = FastAPI()

    @app.get("/admin-only")
    def admin_only(user=Depends(require_admin)):
        return {"ok": True}

    headers = auth_headers()
    # Forge a token that CLAIMS admin; the DB role is still "user".
    s = get_settings()
    uid = client.get("/api/auth/me", headers=headers).json()["id"]
    forged = jwt.encode({"sub": uid, "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        s.jwt_secret, algorithm=s.jwt_algorithm)
    with TestClient(app) as c:
        assert c.get("/admin-only", headers={"Authorization": f"Bearer {forged}"}).status_code == 403
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET role = 'admin'"))
        assert c.get("/admin-only", headers=headers).status_code == 200


def test_profile_update_and_password_change(client, auth_headers):
    headers = auth_headers()
    r = client.patch("/api/auth/me", json={"full_name": "New Name", "preferred_language": "te"}, headers=headers)
    assert r.status_code == 200 and r.json()["preferred_language"] == "te"
    assert client.patch("/api/auth/me", json={"preferred_language": "fr"}, headers=headers).status_code == 422

    bad = client.post("/api/auth/change-password", headers=headers,
                      json={"current_password": "Nope12345", "new_password": "Newpass456"})
    assert bad.status_code == 400
    ok = client.post("/api/auth/change-password", headers=headers,
                     json={"current_password": "Password123", "new_password": "Newpass456"})
    assert ok.status_code == 204
    assert client.post("/api/auth/login", json={"email": "student@example.com",
                                                "password": "Password123"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "student@example.com",
                                                "password": "Newpass456"}).status_code == 200


def test_audit_log_records_auth_events(client, auth_headers):
    headers = auth_headers()
    client.post("/api/auth/login", json={"email": "student@example.com", "password": "Wrong12345"})
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    with engine.connect() as conn:
        actions = [r[0] for r in conn.execute(text("SELECT action FROM audit_logs ORDER BY id"))]
    assert actions[0] == "auth.register"
    for expected in ("auth.login", "auth.login_failed", "auth.logout"):
        assert expected in actions
    with engine.connect() as conn:
        leaked = conn.execute(text("SELECT count(*) FROM audit_logs WHERE details::text ILIKE '%Wrong12345%'")).scalar()
    assert leaked == 0  # passwords never written to the audit log


def test_rate_limit_applies_when_enabled(client):
    from app.core.limiter import limiter
    limiter.enabled = True
    try:
        codes = [client.post("/api/auth/login", json={"email": "a@example.com", "password": "Password123"}).status_code
                 for _ in range(12)]
    finally:
        limiter.enabled = False
        limiter.reset()
    assert 429 in codes


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["pgvector"] is True
