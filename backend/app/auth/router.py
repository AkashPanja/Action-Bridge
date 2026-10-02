from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_active_user, RequirePermission
from app.auth.schemas import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    CreateUserRequest,
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    SetupRequest,
    SetupStatusResponse,
    TokenResponse,
    UpdateUserRequest,
    UserPreferencesUpdate,
    UserResponse,
)
from app.auth.service import (
    authenticate_user,
    check_setup_required,
    create_access_token,
    create_api_key,
    create_initial_admin,
    create_user,
    create_user_by_admin,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    hash_password,
    list_api_keys,
    list_users,
    reset_system,
    revoke_api_key,
    save_setting,
    update_user,
    verify_password,
)
from app.database import get_db
from app.services.email_service import send_email

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(db: AsyncSession = Depends(get_db)):
    required = await check_setup_required(db)
    return SetupStatusResponse(setup_required=required)


@router.post("/setup", response_model=TokenResponse, status_code=201)
async def setup(data: SetupRequest, db: AsyncSession = Depends(get_db)):
    if not await check_setup_required(db):
        raise HTTPException(status_code=409, detail="System is already set up")

    user = await create_initial_admin(db, data)

    await save_setting(db, "company", {
        "name": data.company_name,
        "logo": data.company_logo,
    })

    if data.smtp_host:
        smtp_settings = {
            "host": data.smtp_host,
            "port": data.smtp_port,
            "username": data.smtp_username,
            "password": data.smtp_password,
            "from_email": data.smtp_from_email,
            "use_tls": data.smtp_use_tls,
        }
        await save_setting(db, "smtp", smtp_settings)

    token = create_access_token({"sub": user.id, "role": user.role, "email": user.email})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    return await create_user(db, data)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token({"sub": user.id, "role": user.role, "email": user.email})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def me(user=Depends(get_current_active_user)):
    return user


@router.patch("/me/preferences", response_model=UserResponse)
async def update_preferences(
    data: UserPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    prefs = dict(current_user.preferences or {})
    if data.theme is not None:
        prefs["theme"] = data.theme
    current_user.preferences = prefs
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/me/password", status_code=200)
async def change_password(
    data: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.password_hash = hash_password(data.new_password)
    await db.commit()
    return {"message": "Password updated"}


@router.post("/password-reset", status_code=200)
async def request_password_reset(
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_email(db, data.email)
    if not user:
        return {"message": "If email exists, a reset link has been sent"}
    token = create_access_token({"sub": user.id, "purpose": "password_reset"}, expires_minutes=60)
    from app.config import settings

    reset_link = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
    await send_email(db, data.email, "Password Reset", "password_reset", {
        "name": user.name,
        "reset_link": reset_link,
    })
    return {"message": "If email exists, a reset link has been sent"}


@router.post("/password-reset/confirm", status_code=200)
async def confirm_password_reset(
    data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
):
    from app.auth.service import decode_access_token
    payload = decode_access_token(data.token)
    if not payload or payload.get("purpose") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user = await get_user_by_id(db, payload["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(data.new_password)
    await db.commit()
    return {"message": "Password has been reset"}


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user_endpoint(
    data: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission("users:manage")),
):
    existing = await get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    return await create_user_by_admin(db, data)


@router.get("/users", response_model=list[UserResponse])
async def get_users(
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("users:manage")),
):
    return await list_users(db)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def patch_user(
    user_id: str,
    data: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission("users:manage")),
):
    if user_id == current_user.id and data.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    updated = await update_user(db, user_id, data.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@router.delete("/users/{user_id}", status_code=204)
async def delete_user_endpoint(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(RequirePermission("users:manage")),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    deleted = await delete_user(db, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=201)
async def generate_api_key(
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("api_keys:manage")),
):
    from app.auth.permissions import check_project_permission
    if not await check_project_permission(db, user, data.project_id, "api_keys:manage"):
        raise HTTPException(status_code=403, detail="Missing project permission: api_keys:manage")
    from app.models.api_key_scope import ApiKeyProjectScope
    api_key, raw_key = await create_api_key(db, data.project_id, data.label, data.scopes, project_ids=data.project_ids)
    sr = await db.execute(
        select(ApiKeyProjectScope).where(ApiKeyProjectScope.api_key_id == api_key.id)
    )
    scoped_projects = [s.project_id for s in sr.scalars().all()]
    return ApiKeyCreatedResponse(
        **{k: v for k, v in api_key.__dict__.items() if k != "_sa_instance_state"},
        raw_key=raw_key,
        scoped_projects=scoped_projects,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_project_api_keys(
    project_id: str = Query(),
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("api_keys:manage")),
):
    from app.auth.permissions import check_project_permission
    if not await check_project_permission(db, user, project_id, "api_keys:manage"):
        raise HTTPException(status_code=403, detail="Missing project permission: api_keys:manage")
    return await list_api_keys(db, project_id)


@router.delete("/api-keys/{key_id}", status_code=204)
async def delete_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("api_keys:manage")),
):
    from app.auth.permissions import check_project_permission
    from app.auth.models import ApiKey
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    ak = result.scalar_one_or_none()
    if ak and not await check_project_permission(db, user, ak.project_id, "api_keys:manage"):
        raise HTTPException(status_code=403, detail="Missing project permission: api_keys:manage")
    deleted = await revoke_api_key(db, key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found")


@router.post("/reset", status_code=200)
async def reset(
    db: AsyncSession = Depends(get_db),
    user=Depends(RequirePermission("users:manage")),
):
    await reset_system(db)
    return {"message": "System has been reset"}
