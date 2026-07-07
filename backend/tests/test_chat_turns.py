from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.schemas.domain import AgentClassifyResponse
from src.services.chat_turns import MANUAL_CHOICE_MESSAGE, UNRELATED_MESSAGE, create_chat_turn


@pytest.mark.asyncio
async def test_create_chat_turn_should_persist_user_and_assistant_with_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_messages: list[dict] = []
    title_updates: list[dict] = []

    async def fake_get_chat_session(_: object, user_id: int, session_id: str) -> SimpleNamespace:
        assert user_id == 7
        assert session_id == "CHAT-1"
        return SimpleNamespace(id=session_id, user_id=user_id, title="New device judgment", messages=[])

    async def fake_create_chat_message(
        _: object,
        *,
        session_id: str,
        message_id: str,
        role: str,
        content: str,
        options: list | None = None,
    ) -> SimpleNamespace:
        payload = {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "options": options,
            "created_at": datetime.now(UTC),
        }
        created_messages.append(payload)
        return SimpleNamespace(**payload)

    async def fake_update_title(_: object, user_id: int, session_id: str, title: str) -> None:
        title_updates.append({"user_id": user_id, "session_id": session_id, "title": title})

    async def fake_classify_fault(_: str) -> AgentClassifyResponse:
        return AgentClassifyResponse(
            fault_category="Application failure",
            confidence=0.9,
            message="Application failure response",
            manual_review=False,
            source="langchain",
            fallback_used=False,
        )

    monkeypatch.setattr("src.services.chat_turns.get_chat_session", fake_get_chat_session)
    monkeypatch.setattr("src.services.chat_turns.create_chat_message", fake_create_chat_message)
    monkeypatch.setattr("src.services.chat_turns.update_chat_session_title_and_time", fake_update_title)
    monkeypatch.setattr("src.services.chat_turns.classify_fault", fake_classify_fault)

    user_message, assistant_message = await create_chat_turn(
        SimpleNamespace(),
        user_id=7,
        session_id="CHAT-1",
        message_id="MSG-user",
        assistant_id="MSG-assistant",
        content="Needle issue for P2251212806JND44",
    )

    assert user_message.role == "user"
    assert assistant_message.role == "assistant"
    assert [message["role"] for message in created_messages] == ["user", "assistant"]
    assert not hasattr(assistant_message, "insight") or assistant_message.insight is None
    assert assistant_message.options == [
        {
            "category": "Application failure",
            "title": "Application failure",
            "copy": "Device malfunction may result from assembly or applicator failure.",
            "key": "application-failure",
        }
    ]
    assert title_updates == [
        {"user_id": 7, "session_id": "CHAT-1", "title": "P2251212806JND44"}
    ]


@pytest.mark.asyncio
async def test_create_chat_turn_should_delay_unrelated_cards_until_configured_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_messages: list[dict] = []
    previous_messages = [
        SimpleNamespace(role="user", content="Unrelated question", options=None),
        SimpleNamespace(role="assistant", content=UNRELATED_MESSAGE, options=[]),
        SimpleNamespace(role="user", content="Still unrelated", options=None),
        SimpleNamespace(role="assistant", content=UNRELATED_MESSAGE, options=[]),
    ]

    async def fake_get_chat_session(_: object, user_id: int, session_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=session_id, user_id=user_id, title="Unrelated", messages=previous_messages)

    async def fake_create_chat_message(
        _: object,
        *,
        session_id: str,
        message_id: str,
        role: str,
        content: str,
        options: list | None = None,
    ) -> SimpleNamespace:
        payload = {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "options": options,
            "created_at": datetime.now(UTC),
        }
        created_messages.append(payload)
        return SimpleNamespace(**payload)

    async def fake_update_title(_: object, user_id: int, session_id: str, title: str) -> None:
        return None

    async def fake_classify_fault(_: str) -> AgentClassifyResponse:
        return AgentClassifyResponse(
            fault_category=None,
            intent_type="unrelated",
            confidence=0.7,
            message=UNRELATED_MESSAGE,
            manual_review=True,
            source="langchain",
            fallback_used=False,
        )

    monkeypatch.setattr("src.services.chat_turns.get_chat_session", fake_get_chat_session)
    monkeypatch.setattr("src.services.chat_turns.create_chat_message", fake_create_chat_message)
    monkeypatch.setattr("src.services.chat_turns.update_chat_session_title_and_time", fake_update_title)
    monkeypatch.setattr("src.services.chat_turns.classify_fault", fake_classify_fault)

    _, assistant_message = await create_chat_turn(
        SimpleNamespace(),
        user_id=7,
        session_id="CHAT-1",
        message_id="MSG-user",
        assistant_id="MSG-assistant",
        content="Third unrelated question",
    )

    assert assistant_message.content == MANUAL_CHOICE_MESSAGE
    assert len(assistant_message.options) == 4
