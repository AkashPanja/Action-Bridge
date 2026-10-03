from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import RequirePermission
from app.auth.service import get_setting, save_setting
from app.database import get_db
from app.services.email_service import send_email
from app.schemas.settings import CompanySettings, PasswordPolicy, SettingsResponse, SettingsUpdate, SmtpConfig

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])

DEFAULTS = {
    "company": {"name": "Action Bridge", "logo": ""},
    "smtp": {"host": "", "port": 587, "username": "", "password": "", "from_email": "", "use_tls": True},
    "password_policy": {"min_length": 8, "require_uppercase": True, "require_lowercase": True, "require_numbers": True, "require_symbols": False},
}


@router.get("", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db), user=Depends(RequirePermission("settings:read"))):
    return SettingsResponse(
        company=CompanySettings(**(await get_setting(db, "company") or DEFAULTS["company"])),
        smtp=SmtpConfig(**(await get_setting(db, "smtp") or DEFAULTS["smtp"])),
        password_policy=PasswordPolicy(**(await get_setting(db, "password_policy") or DEFAULTS["password_policy"])),
    )


@router.patch("", response_model=SettingsResponse)
async def update_settings(data: SettingsUpdate, db: AsyncSession = Depends(get_db), user=Depends(RequirePermission("settings:write"))):
    if data.company:
        await save_setting(db, "company", data.company.model_dump())
    if data.smtp:
        await save_setting(db, "smtp", data.smtp.model_dump(exclude_none=True))
    if data.password_policy:
        await save_setting(db, "password_policy", data.password_policy.model_dump())
    return await get_settings(db, user=user)


@router.post("/logo", status_code=200)
async def upload_logo(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user=Depends(RequirePermission("settings:write"))):
    import base64

    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo must be under 2MB")
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in ("image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"):
        raise HTTPException(status_code=400, detail="Logo must be a PNG, JPEG, GIF, WebP, or SVG image")
    b64 = base64.b64encode(content).decode()
    data_uri = f"data:{mime};base64,{b64}"
    existing = await get_setting(db, "company") or {"name": "Action Bridge", "logo": ""}
    existing["logo"] = data_uri
    await save_setting(db, "company", existing)
    return {"logo": data_uri}


@router.post("/test-email", status_code=200)
async def send_test_email(
    db: AsyncSession = Depends(get_db), user=Depends(RequirePermission("settings:write"))
):
    smtp = await get_setting(db, "smtp")
    if not smtp or not smtp.get("host"):
        raise HTTPException(status_code=400, detail="SMTP not configured")
    error = await send_email(
        db,
        to_email=user.email,
        subject="Test Email from Action Bridge",
        template_name="document_approved",
        template_vars={"company_name": (await get_setting(db, "company") or DEFAULTS["company"]).get("name", "Action Bridge")},
    )
    if error:
        raise HTTPException(status_code=502, detail=f"SMTP send failed: {error}")
    return {"message": f"Test email sent to {user.email}"}
