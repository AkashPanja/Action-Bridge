from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import ApiKey, User
from app.auth.service import decode_access_token, get_user_by_id, validate_api_key
from app.database import get_db

bearer_scheme = HTTPBearer(auto_error=False)

PERMISSION_MAP = {
    "projects:read": ["admin", "editor", "viewer"],
    "projects:write": ["admin"],
    "document_types:read": ["admin", "editor", "viewer"],
    "document_types:write": ["admin"],
    "documents:read": ["admin", "editor", "viewer"],
    "documents:write": ["admin", "editor"],
    "documents:approve": ["admin", "editor"],
    "api_keys:manage": ["admin"],
    "users:manage": ["admin"],
    "settings:read": ["admin"],
    "settings:write": ["admin"],
    "credentials:manage": ["admin"],
    "providers:manage": ["admin"],
    "processing:manage": ["admin"],
    "jobs:read": ["admin", "editor", "viewer"],
    "jobs:write": ["admin"],
}


def has_permission(user_role: str, permission: str) -> bool:
    allowed_roles = PERMISSION_MAP.get(permission, [])
    return user_role in allowed_roles


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = await get_user_by_id(db, user_id)
    # Deactivated users lose API access immediately, not at token expiry.
    if user is not None and not user.is_active:
        return None
    return user


async def get_current_active_user(
    current_user: User | None = Depends(get_current_user),
) -> User:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return current_user


class RequirePermission:
    def __init__(self, permission: str):
        self.permission = permission

    async def __call__(self, user: User = Depends(get_current_active_user)):
        if not has_permission(user.role, self.permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {self.permission}",
            )
        return user


async def resolve_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiKey | None:
    api_key_header = request.headers.get("X-API-Key")
    if not api_key_header:
        return None
    return await validate_api_key(db, api_key_header)


async def get_current_user_or_api_key(
    user: User | None = Depends(get_current_user),
    api_key: ApiKey | None = Depends(resolve_api_key),
) -> User | ApiKey:
    if user:
        return user
    if api_key:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide Bearer JWT or X-API-Key header.",
    )


def require_api_key_scope(auth: User | ApiKey, scope: str) -> None:
    """Enforce the scope list on API-key callers (JWT users are covered by
    project permissions checked at each endpoint)."""
    if hasattr(auth, "role"):
        return
    granted = (auth.scopes or {}).get("scopes", []) if isinstance(auth.scopes, dict) else []
    if scope not in granted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key lacks required scope: {scope}",
        )
