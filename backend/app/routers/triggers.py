import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import RequireProjectPermission
from app.database import get_db
from app.models.credential import Credential
from app.models.email_trigger import EmailTrigger, TriggerRun
from app.models.extraction_profile import ExtractionProfile
from app.schemas.extraction import (
    TriggerCreate,
    TriggerDryRunResponse,
    TriggerResponse,
    TriggerRunResponse,
    TriggerUpdate,
)
from app.services import email_poll

router = APIRouter(prefix="/api/v1/projects/{project_id}/triggers", tags=["Triggers"])

VALID_WINDOWS = ("24h", "7d", "30d", "unread")


def _validate_trigger_input(data: dict) -> dict:
    """Normalize + validate trigger fields. Returns cleaned config dict."""
    mode = data.get("mode_override")
    if mode is not None and mode not in ("per_attachment", "combined"):
        raise HTTPException(status_code=400, detail="mode_override must be per_attachment, combined, or null")
    config = data.get("config") or {}
    interval = config.get("poll_interval_s", 300)
    try:
        interval = int(interval)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="poll_interval_s must be an integer")
    if not 60 <= interval <= 86400:
        raise HTTPException(status_code=400, detail="poll_interval_s must be between 60 and 86400")
    config["poll_interval_s"] = interval
    if not (config.get("folder") or "").strip():
        raise HTTPException(status_code=400, detail="folder is required")
    filters = config.get("filters") or {}
    for key in ("subject_pattern", "body_pattern"):
        pattern = (filters.get(key) or "").strip()
        if pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise HTTPException(status_code=400, detail=f"Invalid {key}: {exc}")
    sender = (filters.get("sender") or "").strip()
    if sender.startswith("/") and not (sender.endswith("/") and len(sender) > 2):
        raise HTTPException(status_code=400, detail="sender regex must be wrapped in /.../ ")
    window = (config.get("import_window") or "7d").strip()
    if window not in VALID_WINDOWS and "/" not in window and not window.startswith("20"):
        raise HTTPException(
            status_code=400,
            detail="import_window must be 24h, 7d, 30d, unread, or a date",
        )
    config["import_window"] = window
    received_after = (filters.get("received_after") or "").strip() or None
    if received_after:
        try:
            datetime.fromisoformat(received_after)
        except ValueError:
            raise HTTPException(status_code=400, detail="received_after must be an ISO date")
        filters["received_after"] = received_after
    return config


async def _get_trigger(db: AsyncSession, project_id: str, trigger_id: str) -> EmailTrigger:
    trigger = await db.get(EmailTrigger, trigger_id)
    if not trigger or trigger.project_id != project_id:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return trigger


async def _check_refs(db: AsyncSession, project_id: str, credential_id, profile_id):
    if credential_id:
        cred = await db.get(Credential, credential_id)
        if not cred:
            raise HTTPException(status_code=400, detail="Credential not found")
        if cred.type not in ("basic", "oauth2"):
            raise HTTPException(status_code=400, detail="Mailbox credential must be basic or oauth2 type")
    if profile_id:
        profile = await db.get(ExtractionProfile, profile_id)
        if not profile or profile.project_id != project_id:
            raise HTTPException(status_code=400, detail="Profile not found in this project")


@router.get("", response_model=list[TriggerResponse])
async def list_triggers(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("documents:read")),
):
    result = await db.execute(
        select(EmailTrigger).where(EmailTrigger.project_id == project_id)
        .order_by(EmailTrigger.name)
    )
    return result.scalars().all()


@router.post("", response_model=TriggerResponse, status_code=201)
async def create_trigger(
    project_id: str,
    data: TriggerCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("documents:write")),
):
    payload = data.model_dump()
    config = _validate_trigger_input(payload)
    await _check_refs(db, project_id, payload.get("credential_id"), payload.get("profile_id"))
    trigger = EmailTrigger(
        project_id=project_id,
        name=payload["name"],
        type="email",
        credential_id=payload.get("credential_id"),
        profile_id=payload.get("profile_id"),
        mode_override=payload.get("mode_override"),
        config=config,
        enabled=bool(payload.get("enabled", True)),
        created_by=user.id,
    )
    db.add(trigger)
    await db.commit()
    await db.refresh(trigger)
    return trigger


@router.get("/{trigger_id}", response_model=TriggerResponse)
async def get_trigger(
    project_id: str,
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("documents:read")),
):
    return await _get_trigger(db, project_id, trigger_id)


@router.patch("/{trigger_id}", response_model=TriggerResponse)
async def update_trigger(
    project_id: str,
    trigger_id: str,
    data: TriggerUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("documents:write")),
):
    trigger = await _get_trigger(db, project_id, trigger_id)
    payload = data.model_dump(exclude_unset=True)
    if "mode_override" in payload or "config" in payload:
        merged_config = dict(trigger.config or {})
        if isinstance(payload.get("config"), dict):
            merged_config.update(payload["config"])
        check = {"mode_override": payload.get("mode_override", trigger.mode_override),
                 "config": merged_config}
        merged_config = _validate_trigger_input(check)
        trigger.config = merged_config
    if "name" in payload and payload["name"]:
        trigger.name = payload["name"]
    if "credential_id" in payload or "profile_id" in payload:
        await _check_refs(db, project_id,
                           payload.get("credential_id", trigger.credential_id),
                           payload.get("profile_id", trigger.profile_id))
    if "credential_id" in payload:
        trigger.credential_id = payload["credential_id"]
    if "profile_id" in payload:
        trigger.profile_id = payload["profile_id"]
    if "mode_override" in payload:
        trigger.mode_override = payload["mode_override"]
    if "enabled" in payload and payload["enabled"] is not None:
        trigger.enabled = payload["enabled"]
        if payload["enabled"]:
            state = dict(trigger.state or {})
            state["next_due_at"] = None
            trigger.state = state
    await db.commit()
    await db.refresh(trigger)
    return trigger


@router.delete("/{trigger_id}", status_code=204)
async def delete_trigger(
    project_id: str,
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("documents:write")),
):
    trigger = await _get_trigger(db, project_id, trigger_id)
    await db.delete(trigger)
    await db.commit()
    return None


@router.post("/{trigger_id}/test", response_model=TriggerDryRunResponse)
async def test_trigger(
    project_id: str,
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("documents:write")),
):
    await _get_trigger(db, project_id, trigger_id)
    try:
        return await email_poll.poll_trigger(db, trigger_id, dry_run=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Dry run failed: {exc}")


@router.post("/{trigger_id}/run")
async def run_trigger_now(
    project_id: str,
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("documents:write")),
):
    trigger = await _get_trigger(db, project_id, trigger_id)
    state = dict(trigger.state or {})
    state["next_due_at"] = None
    trigger.state = state
    await db.commit()
    try:
        return await email_poll.poll_trigger(db, trigger_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Run failed: {exc}")


@router.post("/{trigger_id}/pause", response_model=TriggerResponse)
async def pause_trigger(
    project_id: str,
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("documents:write")),
):
    trigger = await _get_trigger(db, project_id, trigger_id)
    trigger.enabled = False
    await db.commit()
    await db.refresh(trigger)
    return trigger


@router.post("/{trigger_id}/resume", response_model=TriggerResponse)
async def resume_trigger(
    project_id: str,
    trigger_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("documents:write")),
):
    trigger = await _get_trigger(db, project_id, trigger_id)
    trigger.enabled = True
    state = dict(trigger.state or {})
    state["next_due_at"] = None
    state["consecutive_failures"] = 0
    state["alert"] = False
    trigger.state = state
    await db.commit()
    await db.refresh(trigger)
    return trigger


@router.get("/{trigger_id}/runs", response_model=list[TriggerRunResponse])
async def list_runs(
    project_id: str,
    trigger_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(RequireProjectPermission("documents:read")),
):
    await _get_trigger(db, project_id, trigger_id)
    result = await db.execute(
        select(TriggerRun).where(TriggerRun.trigger_id == trigger_id)
        .order_by(desc(TriggerRun.started_at)).limit(limit)
    )
    return result.scalars().all()
