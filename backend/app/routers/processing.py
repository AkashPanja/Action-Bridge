from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import RequirePermission
from app.database import get_db
from app.schemas.extraction import ProcessingUpdate
from app.services import processing_service

router = APIRouter(prefix="/api/v1/settings/processing", tags=["Processing"])


@router.get("")
async def get_processing(
    db: AsyncSession = Depends(get_db), user=Depends(RequirePermission("processing:manage"))
):
    return await processing_service.get_settings(db)


@router.put("")
async def put_processing(
    data: ProcessingUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("processing:manage")),
):
    try:
        return await processing_service.update_settings(db, data.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
