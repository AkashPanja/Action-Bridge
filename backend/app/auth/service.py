import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import ApiKey, User
from app.auth.schemas import CreateUserRequest, RegisterRequest, SetupRequest
from app.models.api_key_scope import ApiKeyProjectScope
from app.config import settings
from app.models.audit_event import AuditEvent
from app.models.document_instance import DocumentInstance
from app.models.document_type import DocumentType
from app.models.project import Project
from app.models.settings import AppSetting

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hash: str) -> bool:
    return pwd_context.verify(password, hash)


def create_access_token(data: dict, expires_minutes: int | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email, User.is_active == True))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


DEFAULT_PASSWORD_POLICY = {
    "min_length": 8,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_numbers": True,
    "require_symbols": False,
}


async def validate_password_policy(db: AsyncSession, password: str) -> str | None:
    """Returns an error message when the password violates the stored policy."""
    policy = dict(DEFAULT_PASSWORD_POLICY)
    stored = await get_setting(db, "password_policy")
    if isinstance(stored, dict):
        policy.update({k: v for k, v in stored.items() if k in policy})
    if len(password) < int(policy["min_length"]):
        return f"Password must be at least {policy['min_length']} characters"
    if policy["require_uppercase"] and not any(c.isupper() for c in password):
        return "Password must contain an uppercase letter"
    if policy["require_lowercase"] and not any(c.islower() for c in password):
        return "Password must contain a lowercase letter"
    if policy["require_numbers"] and not any(c.isdigit() for c in password):
        return "Password must contain a number"
    if policy["require_symbols"] and not any(not c.isalnum() for c in password):
        return "Password must contain a symbol"
    return None


async def create_user(db: AsyncSession, data: RegisterRequest) -> User:
    # Open registration can never mint privileged roles (priv-esc guard).
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        role="editor",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def generate_api_key() -> tuple[str, str, str]:
    raw = f"dc_{secrets.token_urlsafe(32)}"
    prefix = raw[:8]
    hashed = pwd_context.hash(raw)
    return raw, hashed, prefix


async def create_api_key(
    db: AsyncSession,
    project_id: str,
    label: str,
    scopes: list[str] | None = None,
    expires_in_days: int | None = None,
    project_ids: list[str] | None = None,
) -> tuple[ApiKey, str]:
    raw_key, key_hash, key_prefix = generate_api_key()
    api_key = ApiKey(
        project_id=project_id,
        label=label,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes={"scopes": scopes or ["documents:write"]},
        expires_at=(
            datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            if expires_in_days
            else None
        ),
    )
    db.add(api_key)
    await db.flush()

    target_projects = project_ids or [project_id]
    for pid in target_projects:
        scope = ApiKeyProjectScope(api_key_id=api_key.id, project_id=pid)
        db.add(scope)

    await db.commit()
    await db.refresh(api_key)
    return api_key, raw_key


async def validate_api_key(db: AsyncSession, raw_key: str) -> ApiKey | None:
    prefix = raw_key[:8]
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_prefix == prefix,
            ApiKey.is_active == True,
        )
    )
    api_keys = result.scalars().all()
    for api_key in api_keys:
        if pwd_context.verify(raw_key, api_key.key_hash):
            if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
                return None
            return api_key
    return None


async def list_api_keys(db: AsyncSession, project_id: str) -> list[dict]:
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.project_id == project_id)
        .order_by(ApiKey.created_at.desc())
    )
    keys = list(result.scalars().all())
    output = []
    for key in keys:
        sr = await db.execute(
            select(ApiKeyProjectScope).where(ApiKeyProjectScope.api_key_id == key.id)
        )
        scoped_projects = [s.project_id for s in sr.scalars().all()]
        output.append({
            "id": key.id,
            "project_id": key.project_id,
            "label": key.label,
            "key_prefix": key.key_prefix,
            "scopes": key.scopes,
            "is_active": key.is_active,
            "expires_at": key.expires_at,
            "created_at": key.created_at,
            "scoped_projects": scoped_projects,
        })
    return output


async def check_setup_required(db: AsyncSession | None = None) -> bool:
    return not os.path.exists(settings.setup_complete_file)


async def create_initial_admin(db: AsyncSession, data: SetupRequest) -> User:
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        role="admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    open(settings.setup_complete_file, "w").close()
    return user


async def save_setting(db: AsyncSession, key: str, value: object) -> AppSetting:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        setting = AppSetting(key=key, value=value)
        db.add(setting)
    await db.commit()
    await db.refresh(setting)
    return setting


async def get_setting(db: AsyncSession, key: str) -> dict | None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else None


async def reset_system(db: AsyncSession) -> None:
    await db.execute(delete(AuditEvent))
    await db.execute(delete(DocumentInstance))
    await db.execute(delete(ApiKey))
    await db.execute(delete(DocumentType))
    await db.execute(delete(AppSetting))
    await db.execute(delete(Project))
    await db.execute(delete(User))
    await db.commit()
    if os.path.exists(settings.setup_complete_file):
        os.remove(settings.setup_complete_file)


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


async def create_user_by_admin(db: AsyncSession, data: CreateUserRequest) -> User:
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: str) -> bool:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return False
    await db.delete(user)
    await db.commit()
    return True


async def update_user(db: AsyncSession, user_id: str, data: dict) -> User | None:
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    for key, val in data.items():
        if val is not None:
            setattr(user, key, val)
    await db.commit()
    await db.refresh(user)
    return user


async def revoke_api_key(db: AsyncSession, key_id: str) -> bool:
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if not api_key:
        return False
    api_key.is_active = False
    await db.commit()
    return True
