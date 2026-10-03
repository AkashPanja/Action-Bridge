import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import RequirePermission, get_current_active_user
from app.auth.permissions import check_project_permission
from app.config import settings
from app.database import get_db
from app.models.document_attachment import DocumentAttachment
from app.models.document_instance import DocumentInstance

router = APIRouter(prefix="/api/v1/attachments", tags=["Attachments"])

RELATIVE_DIR = "attachments"
UPLOAD_DIR = Path(settings.upload_dir) / RELATIVE_DIR
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "text/plain",
    "text/csv",
    "application/json",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Extension is derived from the validated MIME type, never from the
# client-supplied filename — otherwise an attacker can store "evil.html"
# (served back as HTML) while claiming image/png.
MIME_TO_EXT = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


@router.post("/{document_id}", status_code=201)
async def upload_attachment(
    document_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    doc = await db.get(DocumentInstance, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await check_project_permission(db, user, doc.project_id, "documents:attach"):
        raise HTTPException(status_code=403, detail="Missing project permission: documents:attach")

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file.content_type}' not allowed. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB",
        )

    ext = MIME_TO_EXT.get(file.content_type or "")
    if ext is None:
        # Validated above; defense in depth against crafted content types.
        raise HTTPException(status_code=400, detail="File type not allowed")
    stored_name = f"{uuid.uuid4()}{ext}"

    with open(UPLOAD_DIR / stored_name, "wb") as f:
        f.write(content)

    attachment = DocumentAttachment(
        document_id=document_id,
        file_name=file.filename or stored_name,
        file_path=f"{RELATIVE_DIR}/{stored_name}",
        mime_type=file.content_type or "application/octet-stream",
        file_size=len(content),
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    return _format_attachment(attachment)


def _format_attachment(att: DocumentAttachment) -> dict:
    return {
        "id": att.id,
        "document_id": att.document_id,
        "file_name": att.file_name,
        "file_path": att.file_path,
        "mime_type": att.mime_type,
        "file_size": att.file_size,
        "url": f"/uploads/{att.file_path}",
        "created_at": att.created_at.isoformat() if att.created_at else None,
    }


@router.get("/{document_id}")
async def list_attachments(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    doc = await db.get(DocumentInstance, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await check_project_permission(db, user, doc.project_id, "documents:read"):
        raise HTTPException(status_code=403, detail="Missing project permission: documents:read")

    result = await db.execute(
        select(DocumentAttachment)
        .where(DocumentAttachment.document_id == document_id)
        .order_by(DocumentAttachment.created_at.desc())
    )
    return [_format_attachment(a) for a in result.scalars().all()]


@router.delete("/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    result = await db.execute(
        select(DocumentAttachment).where(DocumentAttachment.id == attachment_id)
    )
    att = result.scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    doc = await db.get(DocumentInstance, att.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await check_project_permission(db, user, doc.project_id, "documents:delete"):
        raise HTTPException(status_code=403, detail="Missing project permission: documents:delete")
    full_path = Path(settings.upload_dir) / att.file_path
    try:
        os.remove(str(full_path))
    except OSError:
        pass
    await db.delete(att)
    await db.commit()
