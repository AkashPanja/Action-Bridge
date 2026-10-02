from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_active_user
from app.auth.permissions import check_project_permission
from app.database import get_db
from app.models.submission import Submission, SubmissionFile
from app.schemas.extraction import SubmissionFileResponse, SubmissionResponse
from app.services import ingestion

router = APIRouter(prefix="/api/v1/submissions", tags=["Submissions"])


async def _get_submission(db: AsyncSession, submission_id: str, user) -> Submission:
    submission = await db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    ok = await check_project_permission(db, user, submission.project_id, "documents:read")
    if not ok:
        raise HTTPException(status_code=403, detail="Missing project permission: documents:read")
    return submission


@router.get("/{submission_id}", response_model=SubmissionResponse)
async def get_submission(
    submission_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    submission = await _get_submission(db, submission_id, user)
    files = (await db.execute(
        select(SubmissionFile).where(SubmissionFile.submission_id == submission.id)
        .order_by(SubmissionFile.created_at.asc())
    )).scalars().all()
    return SubmissionResponse(
        id=submission.id,
        project_id=submission.project_id,
        source=submission.source,
        profile_id=submission.profile_id,
        email_meta=submission.email_meta,
        idempotency_key=submission.idempotency_key,
        note=submission.note,
        files=[SubmissionFileResponse.model_validate(f) for f in files],
    )


@router.get("/{submission_id}/files/{file_id}/content")
async def get_file_content(
    submission_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    submission = await _get_submission(db, submission_id, user)
    sfile = await db.get(SubmissionFile, file_id)
    if not sfile or sfile.submission_id != submission.id:
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(sfile.storage_path).resolve()
    root = ingestion.file_store_root().resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing from store")
    return FileResponse(path, media_type=sfile.mime, filename=sfile.filename)
