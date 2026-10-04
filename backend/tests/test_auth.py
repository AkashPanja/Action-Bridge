import os
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestAuthSetup:
    async def test_setup_status_required(self, client: AsyncClient):
        if os.path.exists(".test-setup-complete"):
            os.remove(".test-setup-complete")
        from app.config import settings
        original = settings.setup_complete_file
        settings.setup_complete_file = ".test-setup-complete"

        resp = await client.get("/api/v1/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["setup_required"] is True

        settings.setup_complete_file = original

    async def test_setup_creates_admin(self, client: AsyncClient, setup_required):
        resp = await client.post("/api/v1/auth/setup", json={
            "name": "Initial Admin",
            "email": "initial@test.com",
            "password": "StrongPass1!",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == "initial@test.com"
        assert data["user"]["role"] == "admin"

    async def test_setup_409_when_already_setup(self, client: AsyncClient, setup_complete):
        resp = await client.post("/api/v1/auth/setup", json={
            "name": "Another Admin",
            "email": "another@test.com",
            "password": "StrongPass1!",
        })
        assert resp.status_code == 409
        assert "already" in resp.json()["detail"].lower()


    async def test_setup_required_when_marker_but_no_users(self, client: AsyncClient):
        # Stray marker file (e.g. volume reuse across redeploys) must not
        # dead-end a database with zero users: the wizard is the only screen
        # that can work there.
        import os as _os

        from app.auth.service import check_setup_required
        from app.config import settings
        from app.database import AsyncSessionLocal

        original = settings.setup_complete_file
        settings.setup_complete_file = ".test-setup-complete"
        open(".test-setup-complete", "w").close()
        try:
            async with AsyncSessionLocal() as db:
                assert await check_setup_required(db) is True
            resp = await client.get("/api/v1/auth/status")
            assert resp.json()["setup_required"] is True
            resp = await client.post("/api/v1/auth/setup", json={
                "name": "Fresh Admin",
                "email": "fresh@test.com",
                "password": "StrongPass1!",
            })
            assert resp.status_code == 201
        finally:
            settings.setup_complete_file = original
            if _os.path.exists(".test-setup-complete"):
                _os.remove(".test-setup-complete")


class TestAuthRegister:
    async def test_register_new_user(self, client: AsyncClient, setup_complete):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "newuser@test.com",
            "password": "Pass12345",
            "name": "New User",
            "role": "editor",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@test.com"
        assert data["role"] == "editor"

    async def test_register_duplicate_email(self, client: AsyncClient, setup_complete):
        await client.post("/api/v1/auth/register", json={
            "email": "dup@test.com", "password": "Pass12345", "name": "Dup",
        })
        resp = await client.post("/api/v1/auth/register", json={
            "email": "dup@test.com", "password": "Pass12345", "name": "Dup",
        })
        assert resp.status_code == 409


class TestAuthLogin:
    async def test_login_success(self, client: AsyncClient, setup_complete):
        await client.post("/api/v1/auth/register", json={
            "email": "login@test.com", "password": "Pass12345", "name": "Login",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "email": "login@test.com",
            "password": "Pass12345",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == "login@test.com"

    async def test_login_wrong_password(self, client: AsyncClient, setup_complete):
        await client.post("/api/v1/auth/register", json={
            "email": "wrong@test.com", "password": "Pass12345", "name": "Wrong",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "email": "wrong@test.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    async def test_login_nonexistent(self, client: AsyncClient, setup_complete):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "nobody@test.com",
            "password": "Pass12345",
        })
        assert resp.status_code == 401


class TestAuthMe:
    async def test_me_authenticated(self, client: AsyncClient, admin_headers):
        resp = await client.get("/api/v1/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@test.com"

    async def test_me_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_me_bad_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401


class TestAuthPasswordChange:
    async def test_change_password(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/auth/me/password", headers=admin_headers, json={
            "current_password": "admin123",
            "new_password": "Newpass456",
        })
        assert resp.status_code == 200

    async def test_change_password_wrong_current(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/auth/me/password", headers=admin_headers, json={
            "current_password": "wrongpassword",
            "new_password": "Newpass456",
        })
        assert resp.status_code == 400


class TestAuthPasswordReset:
    async def test_request_reset(self, client: AsyncClient, setup_complete, admin_user):
        resp = await client.post("/api/v1/auth/password-reset", json={
            "email": "admin@test.com",
        })
        assert resp.status_code == 200

    async def test_request_reset_nonexistent(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/password-reset", json={
            "email": "nobody@test.com",
        })
        assert resp.status_code == 200

    async def test_confirm_reset(self, client: AsyncClient, setup_complete, admin_user):
        from app.auth.service import create_access_token
        token = create_access_token({"sub": admin_user.id, "purpose": "password_reset"}, expires_minutes=60)
        resp = await client.post("/api/v1/auth/password-reset/confirm", json={
            "token": token,
            "new_password": "Resetpass123",
        })
        assert resp.status_code == 200

    async def test_confirm_reset_invalid_token(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/password-reset/confirm", json={
            "token": "invalidtokenhere",
            "new_password": "Resetpass123",
        })
        assert resp.status_code == 400


class TestAuthUserManagement:
    async def test_create_user_as_admin(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/auth/users", headers=admin_headers, json={
            "email": "created@test.com",
            "password": "Pass12345",
            "name": "Created User",
            "role": "editor",
        })
        assert resp.status_code == 201
        assert resp.json()["email"] == "created@test.com"

    async def test_create_user_as_reviewer_forbidden(self, client: AsyncClient, editor_headers):
        resp = await client.post("/api/v1/auth/users", headers=editor_headers, json={
            "email": "shouldfail@test.com",
            "password": "Pass12345",
            "name": "Should Fail",
            "role": "editor",
        })
        assert resp.status_code == 403

    async def test_list_users(self, client: AsyncClient, admin_headers):
        resp = await client.get("/api/v1/auth/users", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(u["email"] == "admin@test.com" for u in data)

    async def test_update_user(self, client: AsyncClient, admin_headers, editor_user):
        resp = await client.patch(f"/api/v1/auth/users/{editor_user.id}", headers=admin_headers, json={
            "name": "Updated Name",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_update_user_cannot_deactivate_self(self, client: AsyncClient, admin_headers, admin_user):
        resp = await client.patch(f"/api/v1/auth/users/{admin_user.id}", headers=admin_headers, json={
            "is_active": False,
        })
        assert resp.status_code == 400

    async def test_delete_user(self, client: AsyncClient, admin_headers, editor_user):
        resp = await client.delete(f"/api/v1/auth/users/{editor_user.id}", headers=admin_headers)
        assert resp.status_code == 204

    async def test_delete_user_cannot_delete_self(self, client: AsyncClient, admin_headers, admin_user):
        resp = await client.delete(f"/api/v1/auth/users/{admin_user.id}", headers=admin_headers)
        assert resp.status_code == 400

    async def test_delete_user_not_found(self, client: AsyncClient, admin_headers):
        resp = await client.delete("/api/v1/auth/users/nonexistent-id", headers=admin_headers)
        assert resp.status_code == 404


class TestAuthApiKeys:
    async def test_create_api_key(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/auth/api-keys", headers=admin_headers, json={
            "project_id": "p1",
            "label": "Test Key",
            "scopes": ["documents:write"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["label"] == "Test Key"
        assert "raw_key" in data
        assert data["raw_key"].startswith("dc_")

    async def test_list_api_keys(self, client: AsyncClient, admin_headers):
        await client.post("/api/v1/auth/api-keys", headers=admin_headers, json={
            "project_id": "p1", "label": "Key1",
        })
        resp = await client.get("/api/v1/auth/api-keys?project_id=p1", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1

    async def test_revoke_api_key(self, client: AsyncClient, admin_headers):
        create_resp = await client.post("/api/v1/auth/api-keys", headers=admin_headers, json={
            "project_id": "p1", "label": "ToRevoke",
        })
        key_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=admin_headers)
        assert resp.status_code == 204

    async def test_revoke_api_key_not_found(self, client: AsyncClient, admin_headers):
        resp = await client.delete("/api/v1/auth/api-keys/nonexistent", headers=admin_headers)
        assert resp.status_code == 404

    async def test_api_key_actions_forbidden_for_reviewer(self, client: AsyncClient, editor_headers):
        resp = await client.post("/api/v1/auth/api-keys", headers=editor_headers, json={
            "project_id": "p1", "label": "Blocked",
        })
        assert resp.status_code == 403


class TestAuthReset:
    async def test_reset_system(self, client: AsyncClient, admin_headers, setup_complete):
        await client.post("/api/v1/auth/users", headers=admin_headers, json={
            "email": "temp@test.com", "password": "Pass12345", "name": "Temp",
        })
        resp = await client.post("/api/v1/auth/reset", headers=admin_headers)
        assert resp.status_code == 200
        users_resp = await client.get("/api/v1/auth/users", headers=admin_headers)
        assert users_resp.status_code == 401
