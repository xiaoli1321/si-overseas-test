from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tables import OpenApiIdempotencyKey


async def get_openapi_idempotency_key(
    db: AsyncSession, *, user_id: int, idempotency_key: str
) -> OpenApiIdempotencyKey | None:
    result = await db.execute(
        select(OpenApiIdempotencyKey).where(
            OpenApiIdempotencyKey.user_id == user_id,
            OpenApiIdempotencyKey.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def claim_openapi_idempotency_key(
    db: AsyncSession,
    *,
    user_id: int,
    idempotency_key: str,
    request_hash: str,
    expires_at: datetime,
) -> OpenApiIdempotencyKey | None:
    """Atomically reserve a key; None means another request already owns it."""
    statement = (
        insert(OpenApiIdempotencyKey)
        .values(
            user_id=user_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            expires_at=expires_at,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
        .returning(OpenApiIdempotencyKey)
    )
    return (await db.execute(statement)).scalar_one_or_none()
