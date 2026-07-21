from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, require_manager
from src.core.database import get_db
from src.core.responses import ok
from src.models.tables import User
from src.repositories.store import list_managed_users
from src.schemas.domain import (
    CreateUserRequest,
    LoginRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from src.schemas.frontend import managed_user_to_frontend, user_to_frontend
from src.services.auth import create_user, login, reset_account_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login_endpoint(
    payload: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    token, user = await login(db, payload.email, payload.password)
    return ok(
        {
            **TokenResponse(access_token=token).model_dump(),
            "user": user_to_frontend(user),
        }
    )


@router.get("/me")
async def me_endpoint(user: Annotated[User, Depends(get_current_user)]) -> dict:
    return ok(user_to_frontend(user))


@router.post("/users")
async def create_user_endpoint(
    payload: CreateUserRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    created = await create_user(
        db,
        actor=user,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        distributor_name=payload.distributor_name,
    )
    return ok(user_to_frontend(created))


@router.get("/users")
async def list_users_endpoint(
    manager: Annotated[User, Depends(require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """List the accounts the current manager has provisioned."""
    users = await list_managed_users(db, manager.id)
    return ok([managed_user_to_frontend(u) for u in users])


@router.post("/users/{user_id}/reset-password")
async def reset_password_endpoint(
    user_id: int,
    payload: ResetPasswordRequest,
    manager: Annotated[User, Depends(require_manager)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Reset a managed account's password; returns the new plaintext once."""
    target, password = await reset_account_password(
        db,
        actor=manager,
        target_user_id=user_id,
        new_password=payload.password,
    )
    return ok({"id": str(target.id), "email": target.email, "password": password})
