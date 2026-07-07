import re
import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user
from src.core.database import get_db
from src.core.exceptions import NotFoundError
from src.core.logging import log_context
from src.core.responses import ok
from src.models.tables import User
from src.repositories.chats import (
    create_chat_message,
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    list_chat_sessions,
    update_chat_session_title_and_time,
)
from src.schemas.chats import (
    ChatMessageResponse,
    ChatSessionDetailResponse,
    ChatSessionResponse,
    ChatTurnResponse,
    CreateChatTurnRequest,
    CreateChatSessionRequest,
    SendMessageRequest,
    UpdateChatSessionRequest,
)
from src.services.audit import record_audit_event
from src.services.chat_turns import create_chat_turn

router = APIRouter(prefix="/agent/chats", tags=["chats"])
logger = logging.getLogger(__name__)


@router.get("", response_model=None)
async def list_sessions_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    sessions = await list_chat_sessions(db, user.id)
    logger.info(
        "Chat sessions listed",
        extra=log_context(
            "chat.sessions_listed", user_id=user.id, session_count=len(sessions)
        ),
    )
    return ok(
        [
            ChatSessionResponse.model_validate(s).model_dump(by_alias=True)
            for s in sessions
        ]
    )


@router.post("", response_model=None)
async def create_session_endpoint(
    payload: CreateChatSessionRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    session = await create_chat_session(db, user.id, payload.id, payload.title)
    await record_audit_event(
        db,
        user_id=user.id,
        action="chat.create",
        target_type="chat_session",
        target_id=session.id,
        metadata={"title": session.title},
    )
    await db.commit()
    logger.info(
        "Chat session created",
        extra=log_context(
            "chat.session_created", user_id=user.id, session_id=session.id
        ),
    )
    return ok(ChatSessionResponse.model_validate(session).model_dump(by_alias=True))


@router.get("/{session_id}", response_model=None)
async def get_session_endpoint(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    session = await get_chat_session(db, user.id, session_id)
    if not session:
        raise NotFoundError("Chat session not found")
    logger.info(
        "Chat session loaded",
        extra=log_context(
            "chat.session_loaded", user_id=user.id, session_id=session_id
        ),
    )
    return ok(
        ChatSessionDetailResponse.model_validate(session).model_dump(by_alias=True)
    )


@router.patch("/{session_id}", response_model=None)
async def update_session_endpoint(
    session_id: str,
    payload: UpdateChatSessionRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    session = await get_chat_session(db, user.id, session_id)
    if not session:
        raise NotFoundError("Chat session not found")
    await update_chat_session_title_and_time(db, user.id, session_id, payload.title)
    await db.commit()
    # Fetch updated session
    session = await get_chat_session(db, user.id, session_id)
    logger.info(
        "Chat session updated",
        extra=log_context(
            "chat.session_updated", user_id=user.id, session_id=session_id
        ),
    )
    return ok(ChatSessionResponse.model_validate(session).model_dump(by_alias=True))


@router.delete("/{session_id}", response_model=None)
async def delete_session_endpoint(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    deleted = await delete_chat_session(db, user.id, session_id)
    if not deleted:
        raise NotFoundError("Chat session not found")
    await record_audit_event(
        db,
        user_id=user.id,
        action="chat.delete",
        target_type="chat_session",
        target_id=session_id,
    )
    await db.commit()
    logger.info(
        "Chat session deleted",
        extra=log_context(
            "chat.session_deleted", user_id=user.id, session_id=session_id
        ),
    )
    return ok({"success": True})


@router.post("/{session_id}/messages", response_model=None)
async def add_message_endpoint(
    session_id: str,
    payload: SendMessageRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    session = await get_chat_session(db, user.id, session_id)
    if not session:
        # Chat IDs are generated client-side; materialize the session on first
        # message instead of 404ing (e.g. after a DB reset or an offline create).
        session = await create_chat_session(
            db, user.id, session_id, "New device judgment"
        )

    # Update title if it was default and user sent the first message
    if session.title == "New device judgment" and payload.role == "user":
        sn_match = re.search(r"P\d{10}[A-Z0-9]{5}", payload.content, re.IGNORECASE)
        if sn_match:
            new_title = sn_match.group(0).upper()
        else:
            new_title = payload.content.strip()
            if len(new_title) > 42:
                new_title = f"{new_title[:42]}..."
        await update_chat_session_title_and_time(db, user.id, session_id, new_title)

    message = await create_chat_message(
        db,
        session_id=session_id,
        message_id=payload.id,
        role=payload.role,
        content=payload.content,
        options=payload.options,
    )
    await record_audit_event(
        db,
        user_id=user.id,
        action="chat.message",
        target_type="chat_session",
        target_id=session_id,
        metadata={"message_id": message.id, "role": message.role},
    )
    await db.commit()
    logger.info(
        "Chat message created",
        extra=log_context(
            "chat.message_created",
            user_id=user.id,
            session_id=session_id,
            message_id=message.id,
            role=message.role,
        ),
    )
    return ok(ChatMessageResponse.model_validate(message).model_dump(by_alias=True))


@router.post("/{session_id}/turns", response_model=None)
async def create_turn_endpoint(
    session_id: str,
    payload: CreateChatTurnRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    user_message, assistant_message = await create_chat_turn(
        db,
        user_id=user.id,
        session_id=session_id,
        message_id=payload.id,
        assistant_id=payload.assistant_id,
        content=payload.content,
    )
    await record_audit_event(
        db,
        user_id=user.id,
        action="chat.turn",
        target_type="chat_session",
        target_id=session_id,
        metadata={
            "user_message_id": user_message.id,
            "assistant_message_id": assistant_message.id,
        },
    )
    await db.commit()
    response = ChatTurnResponse(
        user_message=ChatMessageResponse.model_validate(user_message),
        assistant_message=ChatMessageResponse.model_validate(assistant_message),
    )
    logger.info(
        "Chat turn created",
        extra=log_context(
            "chat.turn_created",
            user_id=user.id,
            session_id=session_id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
        ),
    )
    return ok(response.model_dump(by_alias=True))
