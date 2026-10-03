import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import RequirePermission, get_current_active_user, get_current_user_or_api_key, require_api_key_scope
from app.auth.permissions import RequireProjectPermission, check_project_permission, PROJECT_PERMISSION_MATRIX
from app.database import get_db
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    DocumentSubmit,
    DocumentUpdate,
)


def sanitize_csv_cell(value: str | int | float | None) -> str | int | float | None:
    """Neutralize spreadsheet formula injection (OWASP CSV Injection).

    Cells starting with = + - @ (after optional whitespace, incl. tab/CR)
    execute as formulas in Excel/Sheets. A leading apostrophe forces text.
    """
    if not isinstance(value, str):
        return value
    if value.lstrip(" \t\r\n")[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value
from app.schemas.document_type import BulkIds
from app.services import document_service

router = APIRouter(prefix="/api/v1/projects/{project_id}/documents", tags=["Documents"])


@router.post("/document-types/{type_id}", response_model=DocumentResponse, status_code=201)
async def submit_document(
    project_id: str,
    type_id: str,
    data: DocumentSubmit,
    db: AsyncSession = Depends(get_db),
    auth = Depends(get_current_user_or_api_key),
):
    is_user = hasattr(auth, "role")
    if is_user:
        has_perm = await check_project_permission(db, auth, project_id, "documents:submit", log_admin_bypass=False)
        if not has_perm:
            raise HTTPException(status_code=403, detail="Missing project permission: documents:submit")
    else:
        from app.models.api_key_scope import ApiKeyProjectScope
        sr = await db.execute(
            select(ApiKeyProjectScope).where(
                ApiKeyProjectScope.api_key_id == auth.id,
                ApiKeyProjectScope.project_id == project_id,
            )
        )
        if not sr.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="API key not authorized for this project")
        require_api_key_scope(auth, "documents:write")
    actor = getattr(auth, "email", "rpa_bot")
    result = await document_service.submit_document(
        db, project_id, type_id, data.extracted_data, data.confidence_scores, actor
    )
    if isinstance(result, str):
        raise HTTPException(status_code=400, detail=result)
    history = await document_service.get_document_history(db, result.id)
    return DocumentResponse(
        **{k: v for k, v in result.__dict__.items() if k != "_sa_instance_state"},
        history=history,
    )


@router.get("", response_model=list[DocumentListResponse])
async def list_documents(
    project_id: str,
    status: str | None = Query(None),
    document_type_id: str | None = Query(None),
    search: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    confidence_min: float | None = Query(None),
    confidence_max: float | None = Query(None),
    sort_by: str | None = Query(None),
    sort_order: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user = Depends(RequireProjectPermission("documents:read")),
):
    from datetime import datetime
    parsed_date_from = datetime.fromisoformat(date_from) if date_from else None
    parsed_date_to = datetime.fromisoformat(date_to) if date_to else None
    docs = await document_service.list_documents(db, project_id, status, document_type_id, search, parsed_date_from, parsed_date_to, confidence_min, confidence_max, sort_by, sort_order, limit, offset)
    type_names = await document_service.get_type_names(db, [doc.document_type_id for doc in docs if doc.document_type_id])
    return [
        DocumentListResponse(
            **{k: v for k, v in doc.__dict__.items() if k != "_sa_instance_state"},
            document_type_name=type_names.get(doc.document_type_id or ""),
        )
        for doc in docs
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    project_id: str,
    document_id: str,
    include_history: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user = Depends(RequireProjectPermission("documents:read")),
):
    doc = await document_service.get_document(db, document_id, include_history)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found")
    history = None
    if include_history:
        history = await document_service.get_document_history(db, document_id)
    return DocumentResponse(
        **{k: v for k, v in doc.__dict__.items() if k != "_sa_instance_state"},
        history=history,
    )


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    project_id: str,
    document_id: str,
    data: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    actor: str = Query("user"),
    user = Depends(RequireProjectPermission("documents:write")),
):
    doc = await document_service.get_document(db, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found")
    result = await document_service.update_document(
        db, document_id, data.extracted_data, data.status, data.comment, actor
    )
    if isinstance(result, str):
        raise HTTPException(status_code=400, detail=result)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    history = await document_service.get_document_history(db, document_id)
    return DocumentResponse(
        **{k: v for k, v in result.__dict__.items() if k != "_sa_instance_state"},
        history=history,
    )


@router.get("/export")
async def export_documents(
    project_id: str,
    format: str = Query("csv", regex="^(csv|xlsx)$"),
    status: str | None = Query(None),
    document_type_id: str | None = Query(None),
    search: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    confidence_min: float | None = Query(None),
    confidence_max: float | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user = Depends(RequireProjectPermission("documents:read")),
):
    parsed_date_from = datetime.fromisoformat(date_from) if date_from else None
    parsed_date_to = datetime.fromisoformat(date_to) if date_to else None
    headers, rows = await document_service.export_documents(
        db, project_id, format, status, document_type_id, search,
        parsed_date_from, parsed_date_to, confidence_min, confidence_max,
    )

    if format == "xlsx":
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Documents"
        ws.append(headers)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=documents_{project_id[:8]}.xlsx"},
        )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows([[sanitize_csv_cell(v) for v in row] for row in rows])
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=documents_{project_id[:8]}.csv"},
    )


@router.post("/bulk-delete", status_code=200)
async def bulk_delete_documents(
    project_id: str,
    data: BulkIds,
    db: AsyncSession = Depends(get_db),
    user = Depends(RequireProjectPermission("documents:delete")),
):
    count = await document_service.bulk_delete_documents(db, project_id, data.ids)
    return {"deleted": count}


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    project_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user = Depends(RequireProjectPermission("documents:delete")),
):
    deleted = await document_service.delete_document(db, project_id, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
