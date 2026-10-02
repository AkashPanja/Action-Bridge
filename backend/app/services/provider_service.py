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
    if "base_url" in data and data["base_url"]:
        provider.base_url = data["base_url"].rstrip("/")
    if "credential_id" in data:
        if data["credential_id"]:
            cred = await db.get(Credential, data["credential_id"])
            if not cred:
                raise ValueError("Credential not found")
        provider.credential_id = data["credential_id"]
    await db.commit()
    await db.refresh(provider)
    return provider


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
