"""M1 extraction foundations: crypto, credentials, providers, processing, jobs."""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


# --- Crypto unit tests ---

class TestCrypto:
    async def test_roundtrip(self):
        from app.utils.crypto import decrypt_secret, encrypt_secret

        token = encrypt_secret("sk-test-123")
        assert token != "sk-test-123"
        assert decrypt_secret(token) == "sk-test-123"

    async def test_mask(self):
        from app.utils.crypto import mask_secret

        assert mask_secret("sk-test-123") == "****-123"
        assert "sk-test" not in mask_secret("sk-test-123")

    async def test_missing_key(self, monkeypatch):
        import app.utils.crypto as crypto_mod

        monkeypatch.delenv("APP_ENCRYPTION_KEY", raising=False)
        with pytest.raises(Exception):
            crypto_mod.encrypt_secret("x")

    async def test_bad_key(self, monkeypatch):
        import app.utils.crypto as crypto_mod

        monkeypatch.setenv("APP_ENCRYPTION_KEY", "not-a-key")
        with pytest.raises(Exception):
            crypto_mod.encrypt_secret("x")


# --- Credentials ---

API_KEY_PAYLOAD = {"api_key": "sk-test-SECRET123", "notes": "test key"}


async def _create_cred(client: AsyncClient, headers, name="openai", ctype="api_key", payload=None):
    return await client.post("/api/v1/credentials", headers=headers, json={
        "name": name, "type": ctype, "payload": payload or API_KEY_PAYLOAD,
    })


class TestCredentials:
    async def test_create_and_masked(self, client: AsyncClient, admin_headers):
        resp = await _create_cred(client, admin_headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "openai"
        assert data["hint"].endswith("T123")
        body = json.dumps(data)
        assert "sk-test-SECRET123" not in body
        assert "encrypted_payload" not in body

    async def test_list_hides_secrets(self, client: AsyncClient, admin_headers):
        await _create_cred(client, admin_headers)
        resp = await client.get("/api/v1/credentials", headers=admin_headers)
        assert resp.status_code == 200
        assert "sk-test-SECRET123" not in resp.text

    async def test_duplicate_name(self, client: AsyncClient, admin_headers):
        await _create_cred(client, admin_headers)
        resp = await _create_cred(client, admin_headers)
        assert resp.status_code == 400

    async def test_unknown_type(self, client: AsyncClient, admin_headers):
        resp = await _create_cred(client, admin_headers, ctype="magic")
        assert resp.status_code == 400

    async def test_missing_secret(self, client: AsyncClient, admin_headers):
        resp = await _create_cred(client, admin_headers, payload={"notes": "no secret"})
        assert resp.status_code == 400

    async def test_replace_secret(self, client: AsyncClient, admin_headers):
        created = (await _create_cred(client, admin_headers)).json()
        resp = await client.patch(
            f"/api/v1/credentials/{created['id']}", headers=admin_headers,
            json={"payload": {"api_key": "sk-NEW-9999"}},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["hint"].endswith("9999")

    async def test_delete_unused(self, client: AsyncClient, admin_headers):
        created = (await _create_cred(client, admin_headers)).json()
        resp = await client.delete(f"/api/v1/credentials/{created['id']}", headers=admin_headers)
        assert resp.status_code == 204
        assert (await client.get(f"/api/v1/credentials/{created['id']}", headers=admin_headers)).status_code == 404

    async def test_delete_blocked_when_in_use(self, client: AsyncClient, admin_headers):
        created = (await _create_cred(client, admin_headers)).json()
        prov = await client.post("/api/v1/llm-providers", headers=admin_headers, json={
            "name": "p1", "kind": "openai_compatible",
            "base_url": "http://localhost:11434/v1", "is_local": True,
            "credential_id": created["id"], "model": "m",
        })
        assert prov.status_code == 201, prov.text
        resp = await client.delete(f"/api/v1/credentials/{created['id']}", headers=admin_headers)
        assert resp.status_code == 409
        assert "p1" in resp.json()["detail"]

    async def test_viewer_forbidden(self, client: AsyncClient, viewer_headers):
        resp = await _create_cred(client, viewer_headers)
        assert resp.status_code == 403

    async def test_audit_logged(self, client: AsyncClient, admin_headers, db_session):
        from app.models.audit_log import AuditLog

        await _create_cred(client, admin_headers, name="audited")
        rows = (await db_session.execute(
            select(AuditLog).where(AuditLog.action == "credential_create")
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].target_type == "credential"

    async def test_basic_missing_host(self, client: AsyncClient, admin_headers):
        created = (await _create_cred(
            client, admin_headers, name="imap", ctype="basic",
            payload={"username": "u", "password": "p"},
        )).json()
        resp = await client.post(f"/api/v1/credentials/{created['id']}/test", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is False  # no host -> no network attempted


# --- Providers ---

PROVIDER = {
    "name": "local", "kind": "openai_compatible",
    "base_url": "http://localhost:11434/v1", "model": "qwen2.5:3b",
    "is_local": True,
}


class FakeAdapter:
    def __init__(self, text='{"ok": true}', fail=None):
        self._text = text
        self._fail = fail

    async def complete(self, request):
        from app.services.llm.base import LlmResult, ProviderError

        if self._fail:
            raise self._fail
        return LlmResult(text=self._text, tokens_in=5, tokens_out=3, latency_ms=7, json_mode="json_object")


class TestProviders:
    async def test_crud(self, client: AsyncClient, admin_headers):
        created = (await client.post("/api/v1/llm-providers", headers=admin_headers, json=PROVIDER)).json()
        assert created["model"] == "qwen2.5:3b"

        listed = (await client.get("/api/v1/llm-providers", headers=admin_headers)).json()
        assert any(p["name"] == "local" for p in listed)

        updated = (await client.patch(
            f"/api/v1/llm-providers/{created['id']}", headers=admin_headers,
            json={"max_concurrency": 4},
        )).json()
        assert updated["max_concurrency"] == 4

        resp = await client.delete(f"/api/v1/llm-providers/{created['id']}", headers=admin_headers)
        assert resp.status_code == 204

    async def test_bad_kind(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/llm-providers", headers=admin_headers,
                                 json={**PROVIDER, "kind": "telepathy"})
        assert resp.status_code == 400

    async def test_bad_concurrency(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/llm-providers", headers=admin_headers,
                                 json={**PROVIDER, "max_concurrency": 0})
        assert resp.status_code == 400

    async def test_duplicate_name(self, client: AsyncClient, admin_headers):
        await client.post("/api/v1/llm-providers", headers=admin_headers, json=PROVIDER)
        resp = await client.post("/api/v1/llm-providers", headers=admin_headers, json=PROVIDER)
        assert resp.status_code == 400

    async def test_viewer_forbidden(self, client: AsyncClient, viewer_headers):
        resp = await client.post("/api/v1/llm-providers", headers=viewer_headers, json=PROVIDER)
        assert resp.status_code == 403

    async def test_provider_probe_ok(self, client: AsyncClient, admin_headers, monkeypatch):
        import app.services.provider_service as svc

        async def fake_build(db, provider):
            return FakeAdapter()

        monkeypatch.setattr(svc, "build_adapter", fake_build)
        created = (await client.post("/api/v1/llm-providers", headers=admin_headers,
                                     json={**PROVIDER, "json_object": True})).json()
        resp = await client.post(f"/api/v1/llm-providers/{created['id']}/test", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["json_ok"] is True
        assert data["tokens_in"] == 5

    async def test_provider_probe_failure_logged(self, client: AsyncClient, admin_headers, monkeypatch, db_session):
        import app.services.provider_service as svc
        from sqlalchemy import select
        from app.models.provider_call import ProviderCall
        from app.services.llm.base import ProviderError

        async def fake_build(db, provider):
            return FakeAdapter(fail=ProviderError("boom", transient=True))

        monkeypatch.setattr(svc, "build_adapter", fake_build)
        created = (await client.post("/api/v1/llm-providers", headers=admin_headers, json=PROVIDER)).json()
        resp = await client.post(f"/api/v1/llm-providers/{created['id']}/test", headers=admin_headers)
        assert resp.json()["ok"] is False
        calls = (await db_session.execute(select(ProviderCall))).scalars().all()
        assert len(calls) == 1
        assert calls[0].ok is False
        assert calls[0].local is True

    async def test_seed_default_once(self, db_session):
        from app.services.provider_service import ensure_default_provider

        first = await ensure_default_provider(db_session)
        assert first is not None
        assert first.model == "actionbridge-qwen25-3b"
        assert first.is_local is True
        assert await ensure_default_provider(db_session) is None


class TestProviderCloud:
    async def test_presets(self, client: AsyncClient, admin_headers):
        resp = await client.get("/api/v1/llm-providers/presets", headers=admin_headers)
        assert resp.status_code == 200
        presets = resp.json()
        assert len(presets) == 13
        by_id = {p["id"]: p for p in presets}
        assert by_id["openrouter"]["extra_headers"].get("HTTP-Referer")
        assert by_id["anthropic"]["kind"] == "anthropic"
        for preset in presets:
            assert preset["kind"] in ("openai_compatible", "anthropic")
            assert preset["base_url"].startswith("http")

    async def test_viewer_cannot_see_presets(self, client: AsyncClient, viewer_headers):
        assert (await client.get("/api/v1/llm-providers/presets", headers=viewer_headers)).status_code == 403

    async def test_extra_headers_roundtrip(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/llm-providers", headers=admin_headers, json={
            **PROVIDER, "name": "with-headers",
            "extra_headers": {"X-Title": "Action Bridge"},
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["extra_headers"] == {"X-Title": "Action Bridge"}

    async def test_extra_headers_rejects_auth_override(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/llm-providers", headers=admin_headers, json={
            **PROVIDER, "name": "bad-headers",
            "extra_headers": {"Authorization": "Bearer x"},
        })
        assert resp.status_code == 400

    async def test_private_url_needs_local(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/llm-providers", headers=admin_headers, json={
            **PROVIDER, "name": "private-nolocal", "is_local": False,
        })
        assert resp.status_code == 400

    async def test_models_unsupported_kind(self, client: AsyncClient, admin_headers):
        created = (await client.post("/api/v1/llm-providers", headers=admin_headers, json={
            **PROVIDER, "name": "claude", "kind": "anthropic",
            "base_url": "https://api.anthropic.com", "model": "claude-sonnet-4-20250514",
        })).json()
        resp = await client.post(f"/api/v1/llm-providers/{created['id']}/models", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["supported"] is False

    async def test_models_unreachable(self, client: AsyncClient, admin_headers):
        created = (await client.post("/api/v1/llm-providers", headers=admin_headers, json={
            **PROVIDER, "name": "dead", "base_url": "http://localhost:9/v1",
        })).json()
        resp = await client.post(f"/api/v1/llm-providers/{created['id']}/models", headers=admin_headers)
        assert resp.json()["supported"] is False

    async def test_adapter_header_merge(self):
        from app.services.llm.openai_compatible import OpenAiCompatibleAdapter

        adapter = OpenAiCompatibleAdapter(
            base_url="http://x/v1", model="m", api_key="k",
            extra_headers={"X-Title": "Action Bridge"},
        )
        headers = adapter._headers()
        assert headers["Authorization"] == "Bearer k"
        assert headers["X-Title"] == "Action Bridge"

    async def test_factory_passes_headers(self, db_session):
        from app.services.llm.factory import build_adapter
        from app.models.llm_provider import LlmProvider

        provider = LlmProvider(
            name="h", kind="openai_compatible", base_url="http://localhost:11434/v1",
            model="m", is_local=True, extra_headers={"X-A": "b"},
        )
        db_session.add(provider)
        await db_session.commit()
        adapter = await build_adapter(db_session, provider)
        assert adapter.extra_headers == {"X-A": "b"}


class FakeOllamaResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeOllamaStream:
    def __init__(self, lines):
        self._lines = lines
        self.status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeOllamaClient:
    mode = "list"
    lines = ['{"status": "success"}']

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        import httpx as _httpx

        if "unreachable" in url:
            raise _httpx.ConnectError("refused")
        return FakeOllamaResp(200, {"models": [
            {"name": "gemma4:e2b", "size": 4600000000, "modified_at": "2026-10-02T10:00:00Z"},
        ]})

    def stream(self, method, url, **kwargs):
        return FakeOllamaStream(list(FakeOllamaClient.lines))


class TestOllamaEndpoints:
    async def test_list_models(self, client: AsyncClient, admin_headers, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeOllamaClient)
        resp = await client.get(
            "/api/v1/llm-providers/ollama/models",
            headers=admin_headers, params={"base_url": "http://localhost:11434"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["models"][0]["name"] == "gemma4:e2b"

    async def test_list_unreachable(self, client: AsyncClient, admin_headers, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeOllamaClient)
        resp = await client.get(
            "/api/v1/llm-providers/ollama/models",
            headers=admin_headers, params={"base_url": "http://unreachable:11434"},
        )
        assert resp.json()["ok"] is False

    async def test_list_bad_scheme(self, client: AsyncClient, admin_headers):
        resp = await client.get(
            "/api/v1/llm-providers/ollama/models",
            headers=admin_headers, params={"base_url": "ftp://x"},
        )
        assert resp.status_code == 400

    async def test_pull_success(self, client: AsyncClient, admin_headers, monkeypatch):
        FakeOllamaClient.lines = ['{"status": "pulling"}', '{"status": "success"}']
        monkeypatch.setattr("httpx.AsyncClient", FakeOllamaClient)
        resp = await client.post("/api/v1/llm-providers/ollama/pull", headers=admin_headers, json={
            "base_url": "http://localhost:11434", "name": "gemma4:e2b",
        })
        assert resp.json() == {"ok": True, "detail": "Pulled gemma4:e2b."}

    async def test_pull_error(self, client: AsyncClient, admin_headers, monkeypatch):
        FakeOllamaClient.lines = ['{"error": "not found"}']
        monkeypatch.setattr("httpx.AsyncClient", FakeOllamaClient)
        resp = await client.post("/api/v1/llm-providers/ollama/pull", headers=admin_headers, json={
            "base_url": "http://localhost:11434", "name": "nope",
        })
        assert resp.json()["ok"] is False

    async def test_pull_bad_name(self, client: AsyncClient, admin_headers, monkeypatch):
        monkeypatch.setattr("httpx.AsyncClient", FakeOllamaClient)
        resp = await client.post("/api/v1/llm-providers/ollama/pull", headers=admin_headers, json={
            "base_url": "http://localhost:11434", "name": "has space",
        })
        assert resp.json()["ok"] is False

    async def test_viewer_forbidden(self, client: AsyncClient, viewer_headers):
        assert (await client.get("/api/v1/llm-providers/ollama/models", headers=viewer_headers)).status_code == 403


# --- Processing settings ---

class TestProcessing:
    async def test_defaults(self, client: AsyncClient, admin_headers):
        resp = await client.get("/api/v1/settings/processing", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["cpu_workers"] == 4
        assert data["paused"] is False

    async def test_update(self, client: AsyncClient, admin_headers):
        resp = await client.put("/api/v1/settings/processing", headers=admin_headers,
                                json={"cpu_workers": 2, "paused": True})
        assert resp.status_code == 200, resp.text
        assert resp.json()["cpu_workers"] == 2
        assert resp.json()["paused"] is True

    async def test_invalid(self, client: AsyncClient, admin_headers):
        resp = await client.put("/api/v1/settings/processing", headers=admin_headers,
                                json={"cpu_workers": 999})
        assert resp.status_code == 400

    async def test_viewer_forbidden(self, client: AsyncClient, viewer_headers):
        assert (await client.get("/api/v1/settings/processing", headers=viewer_headers)).status_code == 403


# --- Jobs ---

class TestJobs:
    async def test_unknown_kind(self, client: AsyncClient, admin_headers):
        resp = await client.post("/api/v1/jobs", headers=admin_headers, json={"kind": "nope"})
        assert resp.status_code == 400

    async def test_ping_end_to_end(self, client: AsyncClient, admin_headers, db_session):
        from app.services import job_service

        enqueued = (await client.post("/api/v1/jobs", headers=admin_headers,
                                      json={"kind": "ping", "payload": {"echo": "hi"}}))
        assert enqueued.status_code == 201
        job_id = enqueued.json()["id"]

        claimed = await job_service.claim_next(db_session)
        assert claimed is not None
        assert claimed.id == job_id
        await job_service.run_job(claimed.id)

        fetched = (await client.get(f"/api/v1/jobs/{job_id}", headers=admin_headers)).json()
        assert fetched["status"] == "succeeded"
        assert fetched["result"] == {"echo": "hi"}

    async def test_retry_and_cancel(self, client: AsyncClient, admin_headers, db_session):
        from app.services import job_service

        job_id = (await client.post("/api/v1/jobs", headers=admin_headers,
                                    json={"kind": "ping"})).json()["id"]
        claimed = await job_service.claim_next(db_session)
        assert claimed is not None
        # Simulate a cancelled-while-running job then retry it.
        await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=admin_headers)
        state = (await client.get(f"/api/v1/jobs/{job_id}", headers=admin_headers)).json()
        assert state["status"] == "cancelled"

        retried = await client.post(f"/api/v1/jobs/{job_id}/retry", headers=admin_headers)
        assert retried.status_code == 200
        assert retried.json()["status"] == "queued"

        # Retry a queued job is a conflict.
        assert (await client.post(f"/api/v1/jobs/{job_id}/retry", headers=admin_headers)).status_code == 409

    async def test_transient_retry_then_fail(self, client: AsyncClient, admin_headers, db_session, monkeypatch):
        from app.services import job_service
        from app.services.llm.base import ProviderError

        async def flaky(db, job):
            raise ProviderError("timeout", transient=True)

        monkeypatch.setitem(job_service.HANDLERS, "ping", flaky)
        job_id = (await client.post("/api/v1/jobs", headers=admin_headers,
                                    json={"kind": "ping", "max_attempts": 2})).json()["id"]

        first = await job_service.claim_next(db_session)
        await job_service.run_job(first.id)
        state = (await client.get(f"/api/v1/jobs/{job_id}", headers=admin_headers)).json()
        assert state["status"] == "retrying"
        assert state["attempts"] == 1

        # Force the retry to be due now, then run again -> terminal failure.
        from sqlalchemy import update
        from app.models.job import Job

        async with job_service.AsyncSessionLocal() as db:
            await db.execute(update(Job).where(Job.id == job_id).values(next_retry_at=None))
            await db.commit()
        second = await job_service.claim_next(db_session)
        await job_service.run_job(second.id)
        final = (await client.get(f"/api/v1/jobs/{job_id}", headers=admin_headers)).json()
        assert final["status"] == "failed"
        assert "timeout" in final["error"]

    async def test_requeue_running(self, client: AsyncClient, admin_headers):
        from sqlalchemy import update
        from app.models.job import Job
        from app.services import job_service

        job_id = (await client.post("/api/v1/jobs", headers=admin_headers,
                                    json={"kind": "ping"})).json()["id"]
        async with job_service.AsyncSessionLocal() as db:
            await db.execute(update(Job).where(Job.id == job_id).values(status="running"))
            await db.commit()
            revived = await job_service.requeue_running(db)
        assert revived == 1
        state = (await client.get(f"/api/v1/jobs/{job_id}", headers=admin_headers)).json()
        assert state["status"] == "queued"

    async def test_viewer_can_read(self, client: AsyncClient, admin_headers, viewer_headers):
        job_id = (await client.post("/api/v1/jobs", headers=admin_headers,
                                    json={"kind": "ping"})).json()["id"]
        assert (await client.get(f"/api/v1/jobs/{job_id}", headers=viewer_headers)).status_code == 200
        listed = (await client.get("/api/v1/projects/some-id/jobs", headers=viewer_headers)).json()
        assert listed["total"] == 0
