from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.core.security import decode_access_token
from src.models.tables import User
from src.repositories.store import get_user_by_id

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str | None = None,
) -> User:
    token_str = None
    if credentials is not None:
        token_str = credentials.credentials
    elif token is not None:
        token_str = token

    if not token_str:
        raise UnauthorizedError("Missing bearer token.")
    payload = decode_access_token(token_str)
    user = await get_user_by_id(db, int(payload["sub"]))
    if user is None:
        raise UnauthorizedError("User no longer exists.")
    return user


async def require_manager(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency that only lets ``manager`` accounts through.

    Reusable guard for cross-account/admin endpoints (account management,
    dashboards) so the role check lives in one place instead of inline.
    """
    if user.role != "manager":
        raise ForbiddenError("Manager role required.")
    return user
