import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.tables import ChatMessage
from src.repositories.chats import (
    create_chat_message,
    create_chat_session,
    get_chat_session,
    update_chat_session_title_and_time,
)
from src.schemas.domain import AgentClassifyResponse, FaultCategory
from src.services.agent import classify_fault

from src.core.config import get_settings

SN_PATTERN = re.compile(get_settings().sn_regex_pattern, re.IGNORECASE)
UNRELATED_MESSAGE = "Sorry, the issue you describe now is not related to CGM for the time being, please redescribe or consult something related to CGM failure."
MANUAL_CHOICE_MESSAGE = "According to our AIAgent's judgment, the system cannot solve the current user's fault type for the time being, please make a manual judgment."

FAULT_OPTIONS: dict[str, dict[str, str]] = {
    "Data accuracy": {
        "title": "Data accuracy",
        "copy": "Glucose readings differ from BGM, remain flat, stay unusually low, or change suddenly.",
        "key": "data-accuracy",
    },
    "Sensor falling off": {
        "title": "Sensor falling off",
        "copy": "The sensor unexpectedly falls off while the user is wearing it.",
        "key": "sensor-falling-off",
    },
    "Sensor Abnormal": {
        "title": "Sensor Abnormal",
        "copy": "The app homepage shows an error while the sensor is worn correctly.",
        "key": "abnormal-after-warm-up",
    },
    "Application failure": {
        "title": "Application failure",
        "copy": "Device malfunction may result from assembly or applicator failure.",
        "key": "application-failure",
    },
}


def title_from_message(content: str) -> str:
    sn_match = SN_PATTERN.search(content)
    if sn_match:
        return sn_match.group(0).upper()
    title = content.strip()
    return f"{title[:42]}..." if len(title) > 42 else title


def options_for_category(category: FaultCategory | None) -> list[dict[str, str]]:
    if category is None:
        return [{"category": cat, **opt} for cat, opt in FAULT_OPTIONS.items()]
    option = FAULT_OPTIONS[category]
    return [{"category": category, **option}]


def unrelated_turn_count_with_current(
    messages: list[ChatMessage], classification: AgentClassifyResponse
) -> int:
    previous_unrelated_replies = sum(
        1
        for message in messages
        if message.role == "assistant"
        and message.content == UNRELATED_MESSAGE
        and not message.options
    )
    return previous_unrelated_replies + (
        1 if classification.intent_type == "unrelated" else 0
    )


def assistant_reply_for_classification(
    classification: AgentClassifyResponse,
    messages: list[ChatMessage],
) -> tuple[str, list[dict[str, str]]]:
    if classification.fault_category:
        return classification.message, options_for_category(
            classification.fault_category
        )

    if classification.intent_type != "unrelated":
        return classification.message, options_for_category(None)

    settings = get_settings()
    prompt_turns = max(1, settings.agent_unrelated_card_prompt_turns)
    if unrelated_turn_count_with_current(messages, classification) >= prompt_turns:
        return MANUAL_CHOICE_MESSAGE, options_for_category(None)

    return classification.message, []


async def create_chat_turn(
    db: AsyncSession,
    *,
    user_id: int,
    session_id: str,
    message_id: str,
    assistant_id: str,
    content: str,
) -> tuple[ChatMessage, ChatMessage]:
    session = await get_chat_session(db, user_id, session_id)
    if session is None:
        # Chat IDs are generated client-side; materialize the session on first
        # turn instead of 404ing (e.g. after a DB reset or an offline create).
        await create_chat_session(db, user_id, session_id, "New device judgment")
        session = await get_chat_session(db, user_id, session_id)

    user_message = await create_chat_message(
        db,
        session_id=session_id,
        message_id=message_id,
        role="user",
        content=content,
    )
    classification = await classify_fault(content)
    assistant_content, assistant_options = assistant_reply_for_classification(
        classification,
        list(session.messages or []),
    )
    assistant_message = await create_chat_message(
        db,
        session_id=session_id,
        message_id=assistant_id,
        role="assistant",
        content=assistant_content,
        options=assistant_options,
    )

    if session.title == "New device judgment":
        await update_chat_session_title_and_time(
            db,
            user_id,
            session_id,
            title_from_message(content),
        )

    return user_message, assistant_message
