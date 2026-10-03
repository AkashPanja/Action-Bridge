"""Job enqueue/claim/run bookkeeping (FR-9.x). Kind handlers plug in via register()."""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.models.job import JOB_STATUSES, Job
from app.models.submission import SubmissionFile

HANDLERS: dict[str, object] = {}


def register_kind(kind: str, handler):
    """Register an async handler: await handler(db, job) -> (result_dict, usage_dict)."""
    HANDLERS[kind] = handler


async def _ping_handler(db: AsyncSession, job: Job):
    """Built-in smoke-test kind proving the queue end to end (M1)."""
    await asyncio.sleep(0)
    echo = (job.payload or {}).get("echo", "pong")
    return {"echo": echo}, {"tokens_in": 0, "tokens_out": 0}


register_kind("ping", _ping_handler)


async def with_file_summaries(db: AsyncSession, jobs: list[Job]) -> list[dict]:
    """Attach per-file outcomes to jobs (single batched query)."""
    sub_ids = [j.submission_id for j in jobs if j.submission_id]
    files_by_sub: dict[str, list] = {}
    if sub_ids:
        rows = (await db.execute(
            select(SubmissionFile)
            .where(SubmissionFile.submission_id.in_(sub_ids))
            .order_by(SubmissionFile.created_at.asc())
        )).scalars().all()
        for f in rows:
            files_by_sub.setdefault(f.submission_id, []).append({
                "filename": f.filename,
                "status": f.status,
                "skip_reason": f.skip_reason,
                "document_id": f.document_id,
            })
    out = []
    for job in jobs:
        out.append({
            "id": job.id,
            "project_id": job.project_id,
            "submission_id": job.submission_id,
            "kind": job.kind,
            "status": job.status,
            "attempts": job.attempts,
            "error": job.error,
            "provider_id": job.provider_id,
            "payload": job.payload or {},
            "result": job.result,
            "usage": job.usage,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "files": files_by_sub.get(job.submission_id or "", []),
        })
    return out


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue(
    db: AsyncSession,
    kind: str,
    payload: dict | None = None,
    project_id: str | None = None,
    provider_id: str | None = None,
    max_attempts: int = 3,
    submission_id: str | None = None,
) -> Job:
    if kind not in HANDLERS:
        raise ValueError(f"Unknown job kind: {kind}")
    job = Job(
        kind=kind,
        status="queued",
        payload=payload or {},
        project_id=project_id,
        submission_id=submission_id,
        provider_id=provider_id,
        max_attempts=max_attempts,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(db: AsyncSession, job_id: str) -> Job | None:
    return await db.get(Job, job_id)


async def list_jobs(
    db: AsyncSession,
    project_id: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Job], int]:
    query = select(Job)
    count_q = select(func.count()).select_from(Job)
    if project_id:
        query = query.where(Job.project_id == project_id)
        count_q = count_q.where(Job.project_id == project_id)
    if status:
        if status not in JOB_STATUSES:
            raise ValueError(f"Unknown status: {status}")
        query = query.where(Job.status == status)
        count_q = count_q.where(Job.status == status)
    if kind:
        query = query.where(Job.kind == kind)
        count_q = count_q.where(Job.kind == kind)
    total = (await db.execute(count_q)).scalar_one()
    query = query.order_by(Job.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(query)).scalars().all()
    return list(rows), total


async def retry_job(db: AsyncSession, job: Job) -> Job:
    if job.status not in ("failed", "cancelled"):
        raise ValueError(f"Only failed/cancelled jobs can be retried (status={job.status})")
    job.status = "queued"
    job.attempts = 0
    job.error = None
    job.result = None
    job.next_retry_at = None
    job.started_at = None
    job.finished_at = None
    await db.commit()
    await db.refresh(job)
    return job


async def cancel_job(db: AsyncSession, job: Job) -> Job:
    if job.status in ("succeeded", "cancelled"):
        raise ValueError(f"Job is already {job.status}")
    job.status = "cancelled"
    job.finished_at = _utcnow()
    await db.commit()
    await db.refresh(job)
    return job


async def claim_next(db: AsyncSession) -> Job | None:
    """Atomically claim one due job via a single UPDATE...RETURNING.

    Safe for concurrent workers on both engines: the outer status predicate is
    re-checked against the locked row version, so a double-claim matches zero rows.
    """
    now = _utcnow()
    due_ids = (
        select(Job.id)
        .where(
            Job.status.in_(["queued", "retrying"]),
            (Job.next_retry_at.is_(None)) | (Job.next_retry_at <= now),
        )
        .order_by(Job.created_at.asc())
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        update(Job)
        .where(Job.id.in_(due_ids), Job.status.in_(["queued", "retrying"]))
        .values(status="running", started_at=now)
        .returning(Job)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalars().first()


def _backoff_seconds(attempts: int) -> int:
    return min(2 ** max(attempts - 1, 0) * 10, 600)


async def run_job(job_id: str) -> None:
    """Execute one claimed job: handler, retry with backoff, or terminal state."""
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job or job.status != "running":
            return
        handler = HANDLERS.get(job.kind)
        if handler is None:
            job.status = "failed"
            job.error = f"No handler for kind '{job.kind}'"
            job.finished_at = _utcnow()
            await db.commit()
            return
        try:
            result, usage = await handler(db, job)
            # R36: a cancel issued mid-run wins — never overwrite a terminal state.
            await db.refresh(job)
            if job.status != "running":
                return
            job.status = "succeeded"
            job.result = result
            job.usage = usage
            job.error = None
            job.finished_at = _utcnow()
            await db.commit()
        except Exception as exc:  # noqa: BLE001 - worker must never crash on job errors
            await db.refresh(job)
            if job.status not in ("running", "retrying"):
                return  # cancelled meanwhile; leave the terminal state alone
            job.attempts += 1
            transient = getattr(exc, "transient", True)
            if transient and job.attempts < job.max_attempts:
                job.status = "retrying"
                job.error = f"{type(exc).__name__}: {exc}"
                job.next_retry_at = _utcnow() + timedelta(seconds=_backoff_seconds(job.attempts))
            else:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                job.finished_at = _utcnow()
            await db.commit()


async def requeue_running(db: AsyncSession) -> int:
    """Jobs left running (e.g. after a restart) go back to queued (FR-9.4).

    Their in-flight files go back to pending too, otherwise crash recovery
    leaves files stuck in "processing" that no future run will pick up.
    """
    from app.models.submission import SubmissionFile

    stuck = (await db.execute(
        select(Job.id, Job.submission_id).where(Job.status == "running")
    )).all()
    result = await db.execute(
        update(Job)
        .where(Job.status == "running")
        .values(status="queued", started_at=None, next_retry_at=None)
    )
    sub_ids = [row[1] for row in stuck if row[1]]
    if sub_ids:
        await db.execute(
            update(SubmissionFile)
            .where(
                SubmissionFile.submission_id.in_(sub_ids),
                SubmissionFile.status == "processing",
            )
            .values(status="pending")
        )
    await db.commit()
    return result.rowcount or 0
