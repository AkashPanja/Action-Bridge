"""Global (and later per-project) processing settings (FR-3.x)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.processing_setting import DEFAULT_PROCESSING, ProcessingSetting

GLOBAL_SCOPE = "global"

LIMITS = {
    "cpu_workers": (1, 32),
    "max_jobs_in_flight": (1, 128),
    "default_retries": (0, 10),
    "default_timeout_s": (5, 3600),
}


def _validate(values: dict):
    for key, (lo, hi) in LIMITS.items():
        if key in values and values[key] is not None:
            try:
                num = int(values[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be an integer")
            if not lo <= num <= hi:
                raise ValueError(f"{key} must be between {lo} and {hi}")
    if "paused" in values and not isinstance(values["paused"], bool):
        raise ValueError("paused must be a boolean")


async def get_settings(db: AsyncSession, scope: str = GLOBAL_SCOPE) -> dict:
    merged = dict(DEFAULT_PROCESSING)
    result = await db.execute(select(ProcessingSetting).where(ProcessingSetting.scope == scope))
    row = result.scalar_one_or_none()
    if row and row.values:
        merged.update(row.values)
    return merged


async def update_settings(db: AsyncSession, values: dict, scope: str = GLOBAL_SCOPE) -> dict:
    _validate(values)
    result = await db.execute(select(ProcessingSetting).where(ProcessingSetting.scope == scope))
    row = result.scalar_one_or_none()
    if row is None:
        row = ProcessingSetting(scope=scope, values={})
        db.add(row)
        await db.flush()
    merged = dict(row.values or {})
    merged.update({k: v for k, v in values.items() if v is not None})
    row.values = merged
    await db.commit()
    return await get_settings(db, scope)
