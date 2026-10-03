from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import RequirePermission
from app.database import get_db
from app.schemas.extraction import JobEnqueue, JobListResponse, JobResponse
from app.services import job_service

router = APIRouter(tags=["Jobs"])


@router.post("/api/v1/jobs", response_model=JobResponse, status_code=201)
async def enqueue_job(
    data: JobEnqueue,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("jobs:write")),
):
    try:
        job = await job_service.enqueue(
            db,
            kind=data.kind,
            payload=data.payload,
            project_id=data.project_id,
            provider_id=data.provider_id,
            max_attempts=data.max_attempts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return job


@router.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("jobs:read")),
):
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    enriched = await job_service.with_file_summaries(db, [job])
    return enriched[0]


@router.get("/api/v1/projects/{project_id}/jobs", response_model=JobListResponse)
async def list_project_jobs(
    project_id: str,
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("jobs:read")),
):
    try:
        jobs, total = await job_service.list_jobs(db, project_id, status, kind, limit, offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"total": total, "jobs": await job_service.with_file_summaries(db, jobs)}


@router.post("/api/v1/jobs/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("jobs:write")),
):
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        return await job_service.retry_job(db, job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/v1/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("jobs:write")),
):
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        return await job_service.cancel_job(db, job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
