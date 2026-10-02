from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import RequirePermission
from app.database import get_db
from app.models.credential import Credential
from app.schemas.extraction import (
    CredentialCreate,
    CredentialResponse,
    CredentialSecretReplace,
    CredentialTestResponse,
)
from app.services import credential_service
from app.utils.crypto import EncryptionError

router = APIRouter(prefix="/api/v1/credentials", tags=["Credentials"])


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(
    db: AsyncSession = Depends(get_db), user=Depends(RequirePermission("credentials:manage"))
):
    result = await db.execute(select(Credential).order_by(Credential.name))
    return [credential_service.public_view(c) for c in result.scalars().all()]


@router.post("", response_model=CredentialResponse, status_code=201)
async def create_credential(
    data: CredentialCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("credentials:manage")),
):
    try:
        cred = await credential_service.create_credential(
            db, data.name, data.type, data.payload, user.id
        )
    except (ValueError, EncryptionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return credential_service.public_view(cred)


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(
    credential_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("credentials:manage")),
):
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    return credential_service.public_view(cred)


@router.patch("/{credential_id}", response_model=CredentialResponse)
async def replace_secret(
    credential_id: str,
    data: CredentialSecretReplace,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("credentials:manage")),
):
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    try:
        cred = await credential_service.replace_credential_secret(db, cred, data.payload, user.id)
    except (ValueError, EncryptionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return credential_service.public_view(cred)


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("credentials:manage")),
):
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    try:
        await credential_service.delete_credential(db, cred, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return None


@router.post("/{credential_id}/test", response_model=CredentialTestResponse)
async def test_credential(
    credential_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("credentials:manage")),
):
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    try:
        return await credential_service.test_credential(db, cred)
    except Exception as exc:  # noqa: BLE001 - test action must report, not 500
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
