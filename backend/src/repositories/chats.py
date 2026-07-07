from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.utils import string_to_bigint
from src.models.tables import ChatMessage, ChatSession
from src.repositories.scopes import apply_user_scope


async def list_chat_sessions(db: AsyncSession, user_id: int) -> Sequence[ChatSession]:
    query = (
        apply_user_scope(select(ChatSession), ChatSession, user_id)
        .where(ChatSession.messages.any())
        .order_by(ChatSession.updated_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


async def create_chat_session(
    db: AsyncSession, user_id: int, session_id: str, title: str
) -> ChatSession:
    # Idempotent: chat IDs are generated client-side, so the same ID may be
    # created more than once (races, retries, or eager writes before the first
    # message). Return the existing session instead of hitting a PK conflict.
    existing = await get_chat_session(db, user_id, session_id)
    if existing is not None:
        return existing
    session = ChatSession(id=string_to_bigint(session_id), user_id=user_id, title=title)
    db.add(session)
    await db.flush()
    return session


async def get_chat_session(
    db: AsyncSession, user_id: int, session_id: str
) -> ChatSession | None:
    result = await db.execute(
        apply_user_scope(select(ChatSession), ChatSession, user_id)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == string_to_bigint(session_id))
    )
    return result.scalar_one_or_none()


async def delete_chat_session(db: AsyncSession, user_id: int, session_id: str) -> bool:
    session = await get_chat_session(db, user_id, session_id)
    if session:
        await db.delete(session)
        return True
    return False


async def create_chat_message(
    db: AsyncSession,
    session_id: str,
    message_id: str,
    role: str,
    content: str,
    options: list | None = None,
) -> ChatMessage:
    message = ChatMessage(
        id=string_to_bigint(message_id),
        session_id=string_to_bigint(session_id),
        role=role,
        content=content,
        options=options,
    )
    db.add(message)
    await db.flush()
    return message


async def update_chat_session_title_and_time(
    db: AsyncSession, user_id: int, session_id: str, title: str
) -> None:
    query = apply_user_scope(select(ChatSession), ChatSession, user_id).where(
        ChatSession.id == string_to_bigint(session_id)
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()
    if session:
        session.title = title
        session.updated_at = datetime.now(UTC)
        await db.flush()
