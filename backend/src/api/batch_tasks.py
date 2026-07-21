from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_db
from src.core.exceptions import NotFoundError
from src.core.responses import ok
from src.models.tables import User
from src.repositories.store import get_batch_task, get_user_by_id
from src.schemas.domain import BatchTaskResponse
from src.schemas.frontend import batch_to_frontend

router = APIRouter(prefix="/batch-tasks", tags=["batch-tasks"])


@router.get("/{task_id}")
async def detail_endpoint(
    task_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    task = await get_batch_task(db, user.id, task_id, viewer=user)
    if task is None:
        raise NotFoundError("Batch task was not found.")
    owner = await get_user_by_id(db, task.user_id)
    return ok(batch_to_frontend(task, owner or user))
