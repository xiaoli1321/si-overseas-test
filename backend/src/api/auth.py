from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_db
from src.core.responses import ok
from src.models.tables import User
from src.schemas.domain import LoginRequest, TokenResponse, UserResponse
from src.schemas.frontend import user_to_frontend
from src.services.auth import login

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
