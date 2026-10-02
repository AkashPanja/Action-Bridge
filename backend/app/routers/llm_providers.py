from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import RequirePermission
from app.database import get_db
from app.models.llm_provider import LlmProvider
from app.schemas.extraction import ProviderCreate, ProviderModelsResponse, ProviderResponse, ProviderTestResponse, ProviderUpdate
from app.services import provider_service
from app.services.llm.presets import list_presets

router = APIRouter(prefix="/api/v1/llm-providers", tags=["Providers"])


@router.get("/presets", response_model=list[dict])
async def get_presets(user=Depends(RequirePermission("providers:manage"))):
    return list_presets()


@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    db: AsyncSession = Depends(get_db), user=Depends(RequirePermission("providers:manage"))
):
    result = await db.execute(select(LlmProvider).order_by(LlmProvider.name))
    return [provider_service.public_view(p) for p in result.scalars().all()]


@router.post("", response_model=ProviderResponse, status_code=201)
async def create_provider(
    data: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("providers:manage")),
):
    try:
        provider = await provider_service.create_provider(db, data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return provider_service.public_view(provider)


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("providers:manage")),
):
    provider = await db.get(LlmProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider_service.public_view(provider)


@router.patch("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str,
    data: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("providers:manage")),
):
    provider = await db.get(LlmProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    try:
        provider = await provider_service.update_provider(
            db, provider, data.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return provider_service.public_view(provider)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("providers:manage")),
):
    provider = await db.get(LlmProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    await db.delete(provider)
    await db.commit()
    return None


@router.post("/{provider_id}/test", response_model=ProviderTestResponse)
async def test_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("providers:manage")),
):
    provider = await db.get(LlmProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    try:
        return await provider_service.test_provider(db, provider)
    except Exception as exc:  # noqa: BLE001 - test action must report, not 500
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}", "latency_ms": 0}


@router.post("/{provider_id}/models", response_model=ProviderModelsResponse)
async def list_provider_models(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("providers:manage")),
):
    provider = await db.get(LlmProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return await provider_service.list_models(db, provider)
