import asyncio
import base64

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user_or_api_key, require_api_key_scope
from app.auth.permissions import check_project_permission
from app.database import get_db
from app.models.api_key_scope import ApiKeyProjectScope
from app.models.document_type import DocumentType
from app.models.job import Job
from app.schemas.extraction import ExtractAccepted, ExtractCompleted, ExtractRequest
from app.services import ingestion, job_service, pipeline

router = APIRouter(prefix="/api/v1/projects/{project_id}/extract", tags=["Extract"])

MAX_WAIT_SECONDS = 60
MAX_FILES_PER_SUBMISSION = 50


async def _authorize(project_id: str, db: AsyncSession, auth) -> tuple[str | None, str | None]:
    """Returns (user_id, api_key_id). Raises 403 when not allowed to submit."""
    if hasattr(auth, "role"):
        ok = await check_project_permission(db, auth, project_id, "documents:submit", log_admin_bypass=False)
        if not ok:
            raise HTTPException(status_code=403, detail="Missing project permission: documents:submit")
        return auth.id, None
    sr = await db.execute(
        select(ApiKeyProjectScope).where(
            ApiKeyProjectScope.api_key_id == auth.id,
            ApiKeyProjectScope.project_id == project_id,
        )
    )
    if not sr.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="API key not authorized for this project")
    require_api_key_scope(auth, "documents:write")
    return None, auth.id


async def _validate_refs(db: AsyncSession, project_id: str, profile_id: str | None,
                         document_type_id: str | None):
    from app.models.extraction_profile import ExtractionProfile

    if profile_id:
        profile = await db.get(ExtractionProfile, profile_id)
        if not profile or profile.project_id != project_id:
            raise HTTPException(status_code=400, detail="Profile not found in this project")
    if document_type_id:
        dtype = await db.get(DocumentType, document_type_id)
        if not dtype or dtype.project_id != project_id:
            raise HTTPException(status_code=400, detail="Document type not in this project")
    if not profile_id and not document_type_id:
        raise HTTPException(status_code=400, detail="profile_id or document_type_id is required")


async def _submit_batch(
    db: AsyncSession, project_id: str, auth, files: list[tuple[str, bytes]],
    profile_id: str | None, document_type_id: str | None,
    idempotency_key: str | None, callback_url: str | None,
    wait_seconds: int, note: str | None,
):
    await _validate_refs(db, project_id, profile_id, document_type_id)
    if callback_url and ingestion.is_private_url(callback_url):
        raise HTTPException(status_code=400, detail="callback_url targets a private address")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > MAX_FILES_PER_SUBMISSION:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files (max {MAX_FILES_PER_SUBMISSION} per submission)",
        )

    user_id, api_key_id = await _authorize(project_id, db, auth)

    if idempotency_key:
        existing = await pipeline.find_submission_by_key(db, project_id, idempotency_key)
        if existing:
            job = await pipeline.find_job_for_submission(db, existing.id)
            if job:
                return await _maybe_wait(db, job, wait_seconds, project_id)

    submission = await pipeline.intake_files(
        db, project_id, "upload" if user_id else "api", files,
        profile_id=profile_id, document_type_id=document_type_id,
        idempotency_key=idempotency_key, note=note,
        created_by=user_id, api_key_id=api_key_id,
    )
    job = await job_service.enqueue(
        db, "extract",
        {"submission_id": submission.id, "callback_url": callback_url},
        project_id=project_id,
        submission_id=submission.id,
    )
    return await _maybe_wait(db, job, wait_seconds, project_id)


async def _maybe_wait(db: AsyncSession, job: Job, wait_seconds: int, project_id: str):
    wait_seconds = max(0, min(wait_seconds or 0, MAX_WAIT_SECONDS))
    if wait_seconds:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_seconds
        while loop.time() < deadline:
            if job.status in ("succeeded", "failed", "cancelled"):
                break
            await asyncio.sleep(1)
            try:
                await db.refresh(job)
            except Exception:
                break
    if job.status == "succeeded":
        result = job.result or {}
        doc_ids = result.get("document_ids", [])
        return ExtractCompleted(
            job_id=job.id, status=job.status, submission_id=result.get("submission_id", ""),
            document_ids=doc_ids,
            review_urls=[f"/projects/{project_id}/documents/{d}" for d in doc_ids],
        )
    return ExtractAccepted(job_id=job.id, submission_id=(job.submission_id or ""), status=job.status)


@router.post("", response_model=ExtractAccepted | ExtractCompleted, status_code=201)
async def extract_multipart(
    project_id: str,
    files: list[UploadFile] = File(default=[]),
    profile_id: str | None = Form(default=None),
    document_type_id: str | None = Form(default=None),
    idempotency_key: str | None = Form(default=None),
    callback_url: str | None = Form(default=None),
    wait_seconds: int = Form(default=0),
    note: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    auth=Depends(get_current_user_or_api_key),
):
    contents: list[tuple[str, bytes]] = []
    for upload in files:
        raw = await upload.read()
        contents.append((upload.filename or "file", raw))
    return await _submit_batch(
        db, project_id, auth, contents, profile_id, document_type_id,
        idempotency_key, callback_url, wait_seconds, note,
    )


@router.post("/json", response_model=ExtractAccepted | ExtractCompleted, status_code=201)
async def extract_json(
    project_id: str,
    data: ExtractRequest,
    db: AsyncSession = Depends(get_db),
    auth=Depends(get_current_user_or_api_key),
):
    contents: list[tuple[str, bytes]] = []
    for f in data.files:
        try:
            contents.append((f.filename, base64.b64decode(f.content_base64)))
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid base64 for {f.filename}")
    for url in data.urls:
        try:
            filename, raw = await ingestion.fetch_url(url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"URL {url}: {exc}")
        contents.append((filename, raw))
    return await _submit_batch(
        db, project_id, auth, contents, data.profile_id, data.document_type_id,
        data.idempotency_key, data.callback_url, data.wait_seconds, data.note,
    )
