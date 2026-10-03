"""Security regression tests: auth hardening, scopes, uploads, SSRF, CSV, headers."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestRegistrationRole:
    async def test_register_forces_editor(self, client: AsyncClient, setup_complete):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "sneaky@test.com", "password": "SneakyPass1", "name": "Sneak", "role": "admin",
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["role"] == "editor"


class TestPasswordPolicy:
    async def test_weak_password_rejected(self, client: AsyncClient, setup_complete):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "weak@test.com", "password": "short", "name": "Weak",
        })
        assert resp.status_code == 400
        assert "at least" in resp.json()["detail"]

    async def test_password_without_uppercase_rejected(self, client: AsyncClient, setup_complete):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "weak2@test.com", "password": "alllowercase1", "name": "Weak",
        })
        assert resp.status_code == 400
        assert "uppercase" in resp.json()["detail"]

    async def test_change_to_weak_password_rejected(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/auth/me/password", headers=admin_headers, json={
            "current_password": "admin123", "new_password": "weak",
        })
        # Either wrong-current (if fixture password differs) or policy rejection;
        # must never succeed with a weak password.
        assert resp.status_code in (400,)
        if resp.status_code == 400 and "Current password" not in resp.json().get("detail", ""):
            assert "at least" in resp.json()["detail"] or "uppercase" in resp.json()["detail"]


class TestDeactivatedTokens:
    async def test_deactivated_user_token_rejected(
        self, client: AsyncClient, admin_headers, db_session
    ):
        from app.middleware.ratelimit import reset_limiter

        reset_limiter()
        from app.auth.models import User

        # Register via the open endpoint (no admin involvement).
        resp = await client.post("/api/v1/auth/register", json={
            "email": "doomed@test.com", "password": "DoomedPass1", "name": "Doomed",
        })
        assert resp.status_code == 201
        login = await client.post("/api/v1/auth/login", json={
            "email": "doomed@test.com", "password": "DoomedPass1",
        })
        token = login.json()["access_token"]
        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200

        from sqlalchemy import select
        user = (await db_session.execute(
            select(User).where(User.email == "doomed@test.com"))).scalar_one()
        user.is_active = False
        await db_session.commit()

        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 401


class TestRateLimit:
    async def test_login_brute_force_throttled(self, client: AsyncClient):
        from app.middleware.ratelimit import reset_limiter

        reset_limiter()
        statuses = []
        for _ in range(18):
            r = await client.post("/api/v1/auth/login", json={
                "email": "nobody@test.com", "password": "wrongpassword1A",
            })
            statuses.append(r.status_code)
        assert 429 in statuses
        reset_limiter()


class TestApiKeyScopes:
    async def test_key_without_scope_cannot_submit(
        self, client: AsyncClient, admin_headers
    ):
        pid_resp = await client.post("/api/v1/projects", headers=admin_headers, json={"name": "ScopeProj"})
        pid = pid_resp.json()["id"]
        tid = (await client.post(
            f"/api/v1/projects/{pid}/document-types", headers=admin_headers,
            json={"name": "T", "schema_definition": {"type": "object", "properties": {}}},
        )).json()["id"]
        key_resp = await client.post("/api/v1/auth/api-keys", headers=admin_headers, json={
            "project_id": pid, "label": "ReadOnly", "scopes": ["documents:read"],
        })
        raw_key = key_resp.json()["raw_key"]
        resp = await client.post(
            f"/api/v1/projects/{pid}/documents/document-types/{tid}",
            headers={"X-API-Key": raw_key},
            json={"extracted_data": {}},
        )
        assert resp.status_code == 403
        assert "scope" in resp.json()["detail"]

    async def test_key_with_scope_can_submit(
        self, client: AsyncClient, admin_headers
    ):
        pid_resp = await client.post("/api/v1/projects", headers=admin_headers, json={"name": "ScopeProj2"})
        pid = pid_resp.json()["id"]
        tid = (await client.post(
            f"/api/v1/projects/{pid}/document-types", headers=admin_headers,
            json={"name": "T", "schema_definition": {"type": "object", "properties": {}}},
        )).json()["id"]
        key_resp = await client.post("/api/v1/auth/api-keys", headers=admin_headers, json={
            "project_id": pid, "label": "Writer", "scopes": ["documents:write"],
        })
        raw_key = key_resp.json()["raw_key"]
        resp = await client.post(
            f"/api/v1/projects/{pid}/documents/document-types/{tid}",
            headers={"X-API-Key": raw_key},
            json={"extracted_data": {}},
        )
        assert resp.status_code == 201


class TestAttachmentSpoof:
    async def test_html_filename_gets_safe_extension(
        self, client: AsyncClient, admin_headers
    ):
        pid = (await client.post("/api/v1/projects", headers=admin_headers,
                                 json={"name": "SpoofProj"})).json()["id"]
        tid = (await client.post(
            f"/api/v1/projects/{pid}/document-types", headers=admin_headers,
            json={"name": "T", "schema_definition": {"type": "object", "properties": {}}},
        )).json()["id"]
        doc = (await client.post(
            f"/api/v1/projects/{pid}/documents/document-types/{tid}",
            headers=admin_headers, json={"extracted_data": {}},
        )).json()
        resp = await client.post(
            f"/api/v1/attachments/{doc['id']}",
            headers=admin_headers,
            files={"file": ("evil.html", b"<script>alert(1)</script>", "image/png")},
        )
        assert resp.status_code == 201, resp.text
        url = resp.json()["url"]
        assert url.endswith(".png")
        assert ".html" not in url


class TestLogoValidation:
    async def test_non_image_logo_rejected(self, client: AsyncClient, admin_headers):
        resp = await client.post(
            "/api/v1/settings/logo",
            headers=admin_headers,
            files={"file": ("evil.svg", b"<svg></svg>", "text/html")},
        )
        # text/html is not an allowed logo MIME
        assert resp.status_code == 400


class TestCsvSanitization:
    async def test_formula_cells_neutralized(self):
        from app.routers.documents import sanitize_csv_cell

        assert sanitize_csv_cell("=cmd|'/c calc'!A0") == "'=cmd|'/c calc'!A0"
        assert sanitize_csv_cell("+123") == "'+123"
        assert sanitize_csv_cell("  @malicious") == "'  @malicious"
        assert sanitize_csv_cell("-5") == "'-5"
        assert sanitize_csv_cell("normal text") == "normal text"
        assert sanitize_csv_cell("Total 100") == "Total 100"
        assert sanitize_csv_cell(150.0) == 150.0
        assert sanitize_csv_cell(None) is None


class TestSsrfGuards:
    async def test_private_addresses_blocked(self):
        from app.services.ingestion import is_private_url

        assert is_private_url("http://127.0.0.1/x") is True
        assert is_private_url("http://10.0.0.5/x") is True
        assert is_private_url("http://169.254.169.254/latest") is True
        assert is_private_url("http://[::1]/x") is True
        assert is_private_url("http://localhost:8000/x") is True
        assert is_private_url("ftp://example.com/x") is True
        assert is_private_url("http://8.8.8.8/x") is False

    async def test_redirect_to_private_blocked(self, monkeypatch):
        import httpx
        from app.services import ingestion

        seen_urls = []

        class FakeStream:
            status_code = 302
            headers = {"location": "http://169.254.169.254/secret"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def stream(self, method, url, **k):
                seen_urls.append(url)
                return FakeStream()

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        try:
            await ingestion.fetch_url("http://8.8.8.8/start")
            raise AssertionError("should have blocked the redirect")
        except ValueError as exc:
            assert "private" in str(exc)
        assert seen_urls == ["http://8.8.8.8/start"]


class TestSecurityHeaders:
    async def test_headers_present(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"


class TestSecretGuard:
    async def test_default_secret_refused_outside_debug(self, monkeypatch):
        from app import main as main_mod

        monkeypatch.setattr(main_mod.settings, "debug", False)
        monkeypatch.setattr(
            main_mod.settings, "secret_key",
            "change-me-in-production-use-a-long-random-string",
        )
        import pytest as _pytest

        with _pytest.raises(RuntimeError):
            main_mod.ensure_production_secrets()

    async def test_strong_secret_allowed(self, monkeypatch):
        from app import main as main_mod

        monkeypatch.setattr(main_mod.settings, "debug", False)
        monkeypatch.setattr(main_mod.settings, "secret_key", "a" * 40)
        main_mod.ensure_production_secrets()
