"""Email trigger evaluation: filters, dry runs, mailbox polling (FR-6.x)."""

import asyncio
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credential import Credential
from app.models.email_trigger import EmailTrigger, TriggerRun
from app.services import job_service, pipeline
from app.services.email_connectors import (
    ConnectorError,
    EmailConnector,
    MailMessage,
    build_connector,
)
from app.utils.crypto import decrypt_secret
import json

IMPORT_WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

ALERT_AFTER_FAILURES = 5
BACKOFF_CAP_S = 3600


# --- Filters (all configured rules AND-combine) ---

def _match_sender(rule: str, sender: str) -> bool:
    rule = (rule or "").strip()
    if not rule:
        return True
    sender = sender or ""
    if rule.startswith("/") and rule.endswith("/") and len(rule) > 2:
        try:
            return re.search(rule[1:-1], sender, re.IGNORECASE) is not None
        except re.error:
            return False
    if rule.startswith("@"):
        return rule.lower() in sender.lower()
    return rule.lower() == sender.lower()


def _match_pattern(pattern: str, text: str) -> bool:
    if not (pattern or "").strip():
        return True
    try:
        return re.search(pattern, text or "", re.IGNORECASE) is not None
    except re.error:
        return False


def message_matches(filters: dict, msg: MailMessage) -> tuple[bool, str]:
    """Returns (matched, reason). Reason explains the first failing rule."""
    sender = filters.get("sender", "")
    if not _match_sender(sender, msg.sender):
        return False, f"sender {msg.sender!r} does not match {sender!r}"
    if not _match_pattern(filters.get("subject_pattern", ""), msg.subject):
        return False, "subject does not match pattern"
    if not _match_pattern(filters.get("body_pattern", ""), msg.body_text):
        return False, "body does not match pattern"
    if filters.get("must_have_attachment") and not msg.attachments:
        return False, "no attachments"
    return True, "matched"


def attachment_allowed(filters: dict, filename: str, size: int) -> tuple[bool, str]:
    allowed = filters.get("allowed_types") or []
    if allowed:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in [a.lower().lstrip(".") for a in allowed]:
            return False, f"unsupported_type: .{ext or '?'}"
    max_mb = filters.get("max_attachment_mb")
    if max_mb is not None:
        try:
            if size > float(max_mb) * 1024 * 1024:
                return False, f"oversize: {size} bytes"
        except (TypeError, ValueError):
            pass
    return True, ""


# --- Connector wiring ---

async def _connector_for(db: AsyncSession, trigger: EmailTrigger) -> EmailConnector:
    cred = await db.get(Credential, trigger.credential_id) if trigger.credential_id else None
    if not cred:
        raise ConnectorError("Trigger has no mailbox credential")
    kind = "imap"
    if cred.type == "oauth2":
        # OAuth provider selection lives in credential meta (set at connect time).
        kind = (cred.meta or {}).get("email_kind", "imap")
    if kind == "imap":
        if cred.type != "basic":
            raise ConnectorError("IMAP needs a basic (password/app-password) credential")
        try:
            secrets = json.loads(decrypt_secret(cred.encrypted_payload))
        except Exception as exc:
            raise ConnectorError("Stored mailbox secret is unreadable") from exc
        meta = cred.meta or {}
        host = meta.get("host", "")
        if not host:
            raise ConnectorError("Mailbox credential is missing the IMAP host")
        return build_connector(
            "imap",
            host=host,
            port=int(meta.get("port") or 993),
            username=meta.get("username", ""),
            password=secrets.get("password", ""),
        )
    return build_connector(kind)


def _import_since(state: dict, config: dict) -> str | None:
    """IMAP SINCE date for a never-synced trigger, from its import window."""
    if state.get("initialized"):
        return None
    window = (config.get("import_window") or "7d").strip()
    now = datetime.now(timezone.utc)
    if window == "unread":
        return None  # UID search without SINCE; read state untouched on first run
    if window.startswith("20") or "/" in window:
        return window  # explicit date, passed through
    delta = IMPORT_WINDOWS.get(window, IMPORT_WINDOWS["7d"])
    since = now - delta
    # Locale-independent "02-Oct-2026" form (strftime %b follows server locale).
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{since.day:02d}-{months[since.month - 1]}-{since.year}"


# --- Poll one trigger ---

async def _run_record(db: AsyncSession, trigger_id: str, dry_run: bool):
    run = TriggerRun(trigger_id=trigger_id, dry_run=dry_run)
    db.add(run)
    await db.flush()
    return run


async def poll_trigger(db: AsyncSession, trigger_id: str, dry_run: bool = False) -> dict:
    """Poll a mailbox once. Dry runs list matches without side effects."""
    trigger = await db.get(EmailTrigger, trigger_id)
    if not trigger:
        raise ValueError("Trigger not found")
    config = trigger.config or {}
    filters = config.get("filters") or {}
    folder = config.get("folder") or "INBOX"
    run = await _run_record(db, trigger.id, dry_run)
    # Capture PKs while the rows are fresh: the except-block rollback expires
    # every attribute, and reading .id afterwards raises MissingGreenlet.
    trigger_pk, run_pk = trigger.id, run.id

    connector = await _connector_for(db, trigger)
    try:
        # Connectors are blocking (imaplib) — never stall the event loop.
        await asyncio.to_thread(connector.connect)
        try:
            state = dict(trigger.state or {})
            if dry_run:
                uids = await asyncio.to_thread(
                    connector.list_uids, folder, 0,
                    _import_since(state, config),
                )
            else:
                uids = await asyncio.to_thread(
                    connector.list_uids, folder,
                    int(state.get("last_uid") or 0),
                    _import_since(state, config),
                    False,
                )
            run.seen = len(uids)
            matches: list[dict] = []
            created = 0
            enqueued = 0
            max_uid = int(state.get("last_uid") or 0)
            for uid in uids:
                try:
                    uid_int = int(uid)
                except ValueError:
                    continue
                max_uid = max(max_uid, uid_int)
                if dry_run:
                    msg = await asyncio.to_thread(connector.fetch_envelope, uid)
                else:
                    msg = await asyncio.to_thread(connector.fetch_full, uid)
                ok, reason = message_matches(filters, msg)
                if not ok:
                    continue
                run.matched += 1
                if dry_run:
                    matches.append({
                        "uid": uid,
                        "from": msg.sender,
                        "subject": msg.subject,
                        "attachments": [a.filename for a in msg.attachments],
                    })
                    continue
                if await _ingest_email(db, trigger, msg):
                    created += 1
                    enqueued += 1
                await _after_action(connector, config, uid, run)
            if not dry_run:
                state.update({
                    "initialized": True,
                    "last_uid": max_uid,
                    "consecutive_failures": 0,
                    "alert": False,
                    "last_run_at": datetime.now(timezone.utc).isoformat(),
                    "last_error": None,
                    "next_due_at": None,
                })
                trigger.state = state
            run.submissions_created = created
            run.jobs_enqueued = enqueued
            run.finished_at = datetime.now(timezone.utc)
            await db.commit()
            return {
                "seen": run.seen,
                "matched": run.matched,
                "submissions_created": created,
                "jobs_enqueued": enqueued,
                "matches": matches if dry_run else [],
                "error": None,
            }
        finally:
            await asyncio.to_thread(connector.close)
    except Exception as exc:
        await db.rollback()
        await _record_failure(db, trigger_pk, run_pk, exc, dry_run)
        raise


async def _record_failure(db: AsyncSession, trigger_id: str, run_id: str,
                          exc: Exception, dry_run: bool) -> None:
    from datetime import timezone as _tz
    # The rollback above expired every attribute on the ORM rows — only the
    # captured PKs are safe. Re-fetch first, read only fresh rows.
    fresh = await db.get(EmailTrigger, trigger_id)
    fresh_run = await db.get(TriggerRun, run_id)
    if fresh is None or fresh_run is None:
        await db.commit()
        return
    failures = int((fresh.state or {}).get("consecutive_failures", 0)) + 1
    backoff = min(
        int((fresh.config or {}).get("poll_interval_s") or 300) * (2 ** (failures - 1)),
        BACKOFF_CAP_S,
    )
    state = dict(fresh.state or {})
    state.update({
        "consecutive_failures": failures,
        "alert": failures >= ALERT_AFTER_FAILURES,
        "last_error": f"{type(exc).__name__}: {exc}"[:500],
        "last_run_at": datetime.now(_tz.utc).isoformat(),
        "next_due_at": (datetime.now(_tz.utc) + timedelta(seconds=backoff)).isoformat(),
    })
    fresh.state = state
    fresh_run.finished_at = datetime.now(_tz.utc)
    fresh_run.error = f"{type(exc).__name__}: {exc}"[:1000]
    await db.commit()


async def _after_action(connector: EmailConnector, config: dict, uid: str, run: TriggerRun) -> None:
    """Best-effort post-processing. Failures are recorded, never fatal:
    the UID still advances and idempotency guards reprocessing."""
    action = config.get("after_action") or {}
    warnings: list[str] = []
    try:
        if action.get("move_to_folder"):
            await asyncio.to_thread(connector.move, uid, action["move_to_folder"])
        elif action.get("mark_read", True):
            await asyncio.to_thread(connector.mark_read, uid)
    except Exception as exc:  # noqa: BLE001 - best effort by design
        warnings.append(f"after-action failed: {exc}")
    if warnings and run.error:
        run.error = f"{run.error}; {'; '.join(warnings)}"[:1000]
    elif warnings:
        run.error = "; ".join(warnings)[:1000]


async def _ingest_email(db: AsyncSession, trigger: EmailTrigger, msg: MailMessage) -> bool:
    """Create submission (+extract job) for one matched email. Idempotent on
    Message-ID. Returns True when a job was enqueued."""
    key = f"email:{trigger.id}:{msg.message_id or msg.uid}"
    if await pipeline.find_submission_by_key(db, trigger.project_id, key):
        return False
    config = trigger.config or {}
    filters = config.get("filters") or {}
    files: list[tuple[str, bytes]] = []
    skipped: list[str] = []
    for att in msg.attachments:
        ok, reason = attachment_allowed(filters, att.filename, len(att.content))
        if ok:
            files.append((att.filename, att.content))
        else:
            skipped.append(f"{att.filename or 'unnamed'} ({reason})")
    email_meta = {
        "message_id": msg.message_id,
        "from": msg.sender,
        "to": msg.to,
        "subject": msg.subject,
        "date": msg.date,
        "body_text": (msg.body_text or "")[:5000],
        "attachments": [a.filename for a in msg.attachments],
        "skipped": skipped,
    }
    if not files:
        # Nothing passed the attachment filters — no submission, no job.
        # The UID still advances so this email is not retried forever.
        return False
    submission = await pipeline.intake_files(
        db, trigger.project_id, "email", files,
        profile_id=trigger.profile_id,
        idempotency_key=key,
        email_meta=email_meta,
        note=f"from {msg.sender}",
    )
    payload: dict = {"submission_id": submission.id}
    if trigger.mode_override:
        payload["mode_override"] = trigger.mode_override
    job = await job_service.enqueue(
        db, "extract", payload,
        project_id=trigger.project_id,
        submission_id=submission.id,
    )
    return job is not None


async def poll_due_triggers(db: AsyncSession) -> list[dict]:
    """Run every enabled trigger whose backoff window has passed."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EmailTrigger).where(EmailTrigger.enabled == True)  # noqa: E712
    )
    outcomes = []
    for trigger in result.scalars().all():
        state = trigger.state or {}
        next_due = state.get("next_due_at")
        if next_due:
            try:
                if datetime.fromisoformat(next_due) > now:
                    continue
            except ValueError:
                pass
        else:
            interval = int((trigger.config or {}).get("poll_interval_s") or 300)
            last = state.get("last_run_at")
            if last:
                try:
                    if datetime.fromisoformat(last) + timedelta(seconds=interval) > now:
                        continue
                except ValueError:
                    pass
        try:
            summary = await poll_trigger(db, trigger.id)
            outcomes.append({"trigger_id": trigger.id, **summary})
        except Exception as exc:  # noqa: BLE001 - one bad mailbox must not stop others
            outcomes.append({"trigger_id": trigger.id, "error": str(exc)[:300]})
    return outcomes
