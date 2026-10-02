"""LLM provider management: CRUD, test action (FR-1.5), seeding (FR-1.6)."""

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential import Credential
from app.models.llm_provider import PROVIDER_KINDS, LlmProvider
from app.models.provider_call import ProviderCall
from app.services.llm.base import LlmRequest, ProviderError
from app.services.llm.factory import build_adapter
from app.services.llm.openai_compatible import OpenAiCompatibleAdapter

DEFAULT_OLLAMA_URL = "http://localhost:11434/v1"
DEFAULT_LOCAL_MODEL = "actionbridge-qwen25-3b"

PROBE_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def public_view(provider: LlmProvider) -> dict:
    return {
        "id": provider.id,
        "name": provider.name,
        "kind": provider.kind,
        "base_url": provider.base_url,
        "credential_id": provider.credential_id,
        "model": provider.model,
        "vision": provider.vision,
        "json_schema": provider.json_schema,
        "json_object": provider.json_object,
        "max_concurrency": provider.max_concurrency,
        "timeout_s": provider.timeout_s,
        "is_local": provider.is_local,
        "context_window": provider.context_window,
        "enabled": provider.enabled,
        "extra_headers": provider.extra_headers or {},
    }


def _validate(data: dict, partial: bool = False):
    if not partial or "name" in data:
        if not data.get("name"):
            raise ValueError("Provider name is required")
    if not partial or "kind" in data:
        if data.get("kind") not in PROVIDER_KINDS:
            raise ValueError(f"kind must be one of {PROVIDER_KINDS}")
    if not partial or "base_url" in data:
        if not data.get("base_url"):
            raise ValueError("base_url is required")
    if not partial or "model" in data:
        if not data.get("model"):
            raise ValueError("model is required")
    if "max_concurrency" in data and (data["max_concurrency"] or 0) < 1:
        raise ValueError("max_concurrency must be >= 1")
    if "timeout_s" in data and (data["timeout_s"] or 0) <= 0:
        raise ValueError("timeout_s must be positive")
    if "extra_headers" in data and data["extra_headers"] is not None:
        headers = data["extra_headers"]
        if not isinstance(headers, dict) or len(headers) > 20:
            raise ValueError("extra_headers must be an object with at most 20 entries")
        for key, value in headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("extra_headers keys and values must be strings")
            if key.lower() in ("authorization", "content-length", "host"):
                raise ValueError(f"extra_headers must not override {key}")


async def create_provider(db: AsyncSession, data: dict) -> LlmProvider:
    _validate(data)
    existing = await db.execute(select(LlmProvider).where(LlmProvider.name == data["name"]))
    if existing.scalar_one_or_none():
        raise ValueError(f"Provider '{data['name']}' already exists")
    if data.get("credential_id"):
        cred = await db.get(Credential, data["credential_id"])
        if not cred:
            raise ValueError("Credential not found")
        if cred.type != "api_key":
            raise ValueError("Providers require an api_key credential")
    from app.services import ingestion as _ingestion

    _ingestion.validate_provider_url(data["base_url"], bool(data.get("is_local", False)))
    provider = LlmProvider(
        name=data["name"],
        kind=data["kind"],
        base_url=data["base_url"].rstrip("/"),
        credential_id=data.get("credential_id"),
        model=data["model"],
        vision=bool(data.get("vision", False)),
        json_schema=bool(data.get("json_schema", False)),
        json_object=bool(data.get("json_object", False)),
        max_concurrency=int(data.get("max_concurrency") or 1),
        timeout_s=float(data.get("timeout_s") or 120),
        is_local=bool(data.get("is_local", False)),
        context_window=data.get("context_window"),
        enabled=bool(data.get("enabled", True)),
        extra_headers=dict(data.get("extra_headers") or {}),
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider


async def update_provider(db: AsyncSession, provider: LlmProvider, data: dict) -> LlmProvider:
    _validate(data, partial=True)
    if "name" in data and data["name"] != provider.name:
        existing = await db.execute(select(LlmProvider).where(LlmProvider.name == data["name"]))
        if existing.scalar_one_or_none():
            raise ValueError(f"Provider '{data['name']}' already exists")
    for key in ("name", "kind", "model", "vision", "json_schema", "json_object",
                "max_concurrency", "timeout_s", "is_local", "context_window", "enabled"):
        if key in data and data[key] is not None:
            setattr(provider, key, data[key])
    if "extra_headers" in data and data["extra_headers"] is not None:
        if not isinstance(data["extra_headers"], dict):
            raise ValueError("extra_headers must be an object")
        provider.extra_headers = data["extra_headers"]
    if "base_url" in data and data["base_url"]:
        provider.base_url = data["base_url"].rstrip("/")
    if "credential_id" in data:
        if data["credential_id"]:
            cred = await db.get(Credential, data["credential_id"])
            if not cred:
                raise ValueError("Credential not found")
        provider.credential_id = data["credential_id"]
    from app.services import ingestion as _ingestion

    _ingestion.validate_provider_url(provider.base_url, bool(provider.is_local))
    await db.commit()
    await db.refresh(provider)
    return provider


async def list_models(db: AsyncSession, provider: LlmProvider) -> dict:
    """Query the OpenAI-compatible /models endpoint for a picker (graceful fallback)."""
    import httpx

    if provider.kind != "openai_compatible":
        return {"supported": False, "models": [],
                "detail": "Model listing is only available for OpenAI-compatible providers."}
    adapter = await build_adapter(db, provider)
    base_url = adapter.base_url if isinstance(adapter, OpenAiCompatibleAdapter) else provider.base_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if isinstance(adapter, OpenAiCompatibleAdapter):
        headers = adapter._headers()
    try:
        async with httpx.AsyncClient(timeout=min(provider.timeout_s, 30)) as client:
            resp = await client.get(f"{base_url}/models", headers=headers)
    except httpx.HTTPError as exc:
        return {"supported": False, "models": [], "detail": f"Could not reach /models: {exc}"}
    if resp.status_code != 200:
        return {"supported": False, "models": [],
                "detail": f"/models returned {resp.status_code}"}
    try:
        ids = [m.get("id") for m in resp.json().get("data", []) if m.get("id")]
    except ValueError:
        return {"supported": False, "models": [], "detail": "Non-JSON /models response."}
    return {"supported": True, "models": sorted(ids), "detail": f"{len(ids)} model(s) found."}


def _ollama_base(base_url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Ollama URL must be http(s)")
    if parsed.username or parsed.password:
        raise ValueError("Ollama URL must not contain credentials")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("Ollama URL needs a host")
    # Strip a trailing /v1 (OpenAI-compat base) back to the Ollama root.
    root = f"{parsed.scheme}://{host}"
    if parsed.port:
        root += f":{parsed.port}"
    return root


async def list_ollama_models(base_url: str) -> dict:
    """List models installed on an Ollama server (no auth needed)."""
    import httpx

    root = _ollama_base(base_url)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{root}/api/tags")
    except httpx.HTTPError as exc:
        return {"ok": False, "models": [], "detail": f"Could not reach Ollama: {exc}"}
    if resp.status_code != 200:
        return {"ok": False, "models": [], "detail": f"Ollama returned {resp.status_code}"}
    try:
        models = [
            {"name": m.get("name", ""), "size": m.get("size", 0),
             "modified": (m.get("modified_at") or "")[:10]}
            for m in resp.json().get("models", [])
            if m.get("name")
        ]
    except ValueError:
        return {"ok": False, "models": [], "detail": "Non-JSON response from Ollama."}
    return {"ok": True, "models": sorted(models, key=lambda m: m["name"]),
            "detail": f"{len(models)} model(s) installed."}


async def pull_ollama_model(base_url: str, name: str) -> dict:
    """Pull (download) a model into Ollama. Consumes the progress stream."""
    import httpx

    root = _ollama_base(base_url)
    name = (name or "").strip()
    if not name or len(name) > 200 or any(ch.isspace() for ch in name):
        return {"ok": False, "detail": "Invalid model name."}
    try:
        async with httpx.AsyncClient(timeout=60 * 20) as client:
            async with client.stream("POST", f"{root}/api/pull", json={"name": name, "stream": True}) as resp:
                if resp.status_code != 200:
                    return {"ok": False, "detail": f"Ollama returned {resp.status_code}"}
                last: dict = {}
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        import json as _json

                        last = _json.loads(line)
                    except ValueError:
                        continue
                    if last.get("error"):
                        return {"ok": False, "detail": last["error"]}
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"Pull failed: {exc}"}
    if "success" in str(last.get("status", "")).lower():
        return {"ok": True, "detail": f"Pulled {name}."}
    return {"ok": False, "detail": f"Pull did not complete: {last.get('status', 'unknown')}"}


async def log_call(
    db: AsyncSession,
    provider: LlmProvider,
    ok: bool,
    latency_ms: int,
    tokens_in: int | None,
    tokens_out: int | None,
    error: str | None = None,
    job_id: str | None = None,
) -> None:
    db.add(ProviderCall(
        provider_id=provider.id,
        job_id=job_id,
        local=provider.is_local,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        ok=ok,
        error=(error or "")[:2000] if error else None,
    ))
    await db.commit()


async def test_provider(db: AsyncSession, provider: LlmProvider) -> dict:
    """Tiny prompt probe: success, latency, JSON-mode support (FR-1.5)."""
    adapter = await build_adapter(db, provider)
    started = time.perf_counter()
    try:
        result = await adapter.complete(LlmRequest(
            messages=[{"role": "user", "content": 'Reply with exactly: {"ok": true}'}],
            schema=PROBE_SCHEMA if (provider.json_schema or provider.json_object) else None,
            timeout_s=min(provider.timeout_s, 60),
        ))
        latency = int((time.perf_counter() - started) * 1000)
    except ProviderError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        await log_call(db, provider, False, latency, None, None, str(exc))
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}", "latency_ms": latency}

    json_ok = False
    try:
        parsed = OpenAiCompatibleAdapter.parse_json(result.text)
        json_ok = parsed.get("ok") is True
    except Exception:
        json_ok = False

    await log_call(db, provider, True, latency, result.tokens_in, result.tokens_out)
    return {
        "ok": True,
        "detail": f"Model '{provider.model}' answered in {latency} ms.",
        "latency_ms": latency,
        "json_mode": result.json_mode,
        "json_ok": json_ok,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
    }


async def ensure_default_provider(db: AsyncSession) -> LlmProvider | None:
    """Seed the local Ollama provider on first start (FR-1.6). Idempotent."""
    existing = await db.execute(select(LlmProvider).limit(1))
    if existing.scalars().first():
        return None
    provider = LlmProvider(
        name="Local Ollama",
        kind="openai_compatible",
        base_url=DEFAULT_OLLAMA_URL,
        credential_id=None,
        model=DEFAULT_LOCAL_MODEL,
        vision=False,
        json_schema=False,
        json_object=True,
        max_concurrency=1,
        timeout_s=180,
        is_local=True,
        context_window=8192,
        enabled=True,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider
