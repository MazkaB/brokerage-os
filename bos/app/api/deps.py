"""
Shared FastAPI dependencies: authentication & settings.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from ..config import Settings, get_settings
from ..security import AuthContext, authenticate_api_key, authenticate_user


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    """Require a valid BOS_API_KEY (via X-API-Key header or ?api_key= query).

    For local/demo we also accept the demo usernames via `X-BOS-User` so
    the dashboard can impersonate different roles.
    """
    api_key = x_api_key
    if not api_key and authorization and authorization.lower().startswith("bearer "):
        api_key = authorization.split(" ", 1)[1]
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    ctx = authenticate_api_key(api_key, settings)
    if not ctx.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return ctx
