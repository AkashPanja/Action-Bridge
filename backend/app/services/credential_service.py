"""Credential CRUD with encryption, write-only secrets, and audit trail (FR-2.x)."""

import asyncio
import imaplib
import json
import ssl

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.credential import CREDENTIAL_TYPES, Credential
from app.models.llm_provider import LlmProvider
from app.utils.crypto import decrypt_secret, encrypt_secret, mask_secret

# Secret field per credential type. Everything else in the payload is non-secret
# metadata and is NOT stored.
SECRET_FIELDS = {
    "api_key": ("api_key",),
    "basic": ("password",),
    "oauth2": ("client_secret", "refresh_token"),
}


def _split_payload(cred_type: str, payload: dict) -> tuple[dict, dict]:
    """Returns (meta, secrets)."""
    secret_keys = set(SECRET_FIELDS.get(cred_type, ()))
    meta = {k: v for k, v in payload.items() if k not in secret_keys}
    secrets = {k: payload.get(k, "") for k in secret_keys}
    return meta, secrets


def _primary_secret(cred_type: str, secrets: dict) -> str:
    first = SECRET_FIELDS.get(cred_type, ("api_key",))[0]
    return str(secrets.get(first, ""))


def public_view(cred: Credential) -> dict:
    return {
        "id": cred.id,
        "name": cred.name,
        "type": cred.type,
        "meta": cred.meta or {},
        "hint": cred.hint,
        "created_by": cred.created_by,
        "created_at": cred.created_at.isoformat() if cred.created_at else None,
        "updated_at": cred.updated_at.isoformat() if cred.updated_at else None,
    }


async def _audit(db: AsyncSession, actor_id: str | None, action: str, cred: Credential):
    db.add(AuditLog(
        actor_id=actor_id,
        action=action,
        target_type="credential",
        target_id=cred.id,
        details={"name": cred.name, "type": cred.type},
    ))


async def create_credential(
    db: AsyncSession, name: str, cred_type: str, payload: dict, actor_id: str | None
) -> Credential:
    if cred_type not in CREDENTIAL_TYPES:
        raise ValueError(f"Unknown credential type: {cred_type}")
    existing = await db.execute(select(Credential).where(Credential.name == name))
    if existing.scalar_one_or_none():
        raise ValueError(f"Credential '{name}' already exists")
    meta, secrets = _split_payload(cred_type, payload)
    if not _primary_secret(cred_type, secrets):
        raise ValueError("Missing secret value")
    cred = Credential(
        name=name,
        type=cred_type,
        meta=meta,
        encrypted_payload=encrypt_secret(json.dumps(secrets)),
        hint=mask_secret(_primary_secret(cred_type, secrets)),
    )
    db.add(cred)
    await db.flush()
    await _audit(db, actor_id, "credential_create", cred)
    await db.commit()
    await db.refresh(cred)
    return cred


async def replace_credential_secret(
    db: AsyncSession, cred: Credential, payload: dict, actor_id: str | None
) -> Credential:
    _, secrets = _split_payload(cred.type, payload)
    # Merge with existing secrets so rotation can update one field at a time.
    try:
        current = json.loads(decrypt_secret(cred.encrypted_payload))
    except Exception:
        current = {}
    current.update({k: v for k, v in secrets.items() if v})
    if not _primary_secret(cred.type, current):
        raise ValueError("Missing secret value")
    cred.encrypted_payload = encrypt_secret(json.dumps(current))
    cred.hint = mask_secret(_primary_secret(cred.type, current))
    if "notes" in payload:
        meta = dict(cred.meta or {})
        meta["notes"] = payload["notes"]
        cred.meta = meta
    await _audit(db, actor_id, "credential_update", cred)
    await db.commit()
    await db.refresh(cred)
    return cred


async def credential_in_use(db: AsyncSession, cred_id: str) -> list[str]:
    """Names of providers referencing the credential (triggers added in M3)."""
    result = await db.execute(
        select(LlmProvider.name).where(LlmProvider.credential_id == cred_id)
    )
    return list(result.scalars().all())


async def delete_credential(db: AsyncSession, cred: Credential, actor_id: str | None) -> None:
    users = await credential_in_use(db, cred.id)
    if users:
        raise ValueError(f"Credential is in use by: {', '.join(users)}")
    await _audit(db, actor_id, "credential_delete", cred)
    await db.delete(cred)
    await db.commit()


async def test_credential(db: AsyncSession, cred: Credential) -> dict:
    """Test connection per credential type (FR-2.4). No secrets in output."""
    if cred.type == "basic":
        return await _test_imap(cred)
    if cred.type == "api_key":
        users = await credential_in_use(db, cred.id)
        if not users:
            return {"ok": True, "detail": "Secret stored. Link it to a provider to test delivery."}
        from app.services.llm.factory import build_adapter
        from app.services.llm.base import LlmRequest

        provider = (await db.execute(
            select(LlmProvider).where(LlmProvider.credential_id == cred.id)
        )).scalars().first()
        adapter = await build_adapter(db, provider)
        import time

        started = time.perf_counter()
        result = await adapter.complete(LlmRequest(
            messages=[{"role": "user", "content": 'Reply with exactly: {"ok": true}'}],
            timeout_s=30,
        ))
        latency = int((time.perf_counter() - started) * 1000)
        parsed = result.text.strip() == '{"ok": true}'
        return {"ok": True, "detail": f"Provider '{provider.name}' answered in {latency} ms.", "latency_ms": latency, "parsed": parsed}
    return {"ok": False, "detail": "OAuth2 testing requires the provider OAuth flow (not in M1)."}


async def _test_imap(cred: Credential) -> dict:
    import asyncio

    meta = cred.meta or {}
    host = meta.get("host", "")
    port = int(meta.get("port") or 993)
    username = meta.get("username", "")
    if not host or not username:
        return {"ok": False, "detail": "Basic credential needs host, port and username in metadata."}
    try:
        secrets = json.loads(decrypt_secret(cred.encrypted_payload))
    except Exception:
        return {"ok": False, "detail": "Stored secret is unreadable."}
    password = secrets.get("password", "")

    def _login() -> int:
        ctx = ssl.create_default_context()
        with imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=20) as conn:
            typ, _ = conn.login(username, password)
            if typ != "OK":
                raise RuntimeError(f"IMAP login returned {typ}")
            _, count = conn.select("INBOX", readonly=True)
            return int(count[0]) if count and count[0].isdigit() else 0

    try:
        messages = await asyncio.to_thread(_login)
    except Exception as exc:
        return {"ok": False, "detail": f"IMAP login failed: {exc}"}
    return {"ok": True, "detail": f"IMAP login OK. INBOX holds {messages} message(s)."}
