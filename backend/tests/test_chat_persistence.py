import pytest
from uuid import uuid4
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_chat_persistence_workflow() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Log in to get access token
        login_response = await ac.post(
            "/api/v1/auth/login",
            json={"email": "christest@sibionics.com", "password": "password123"},
        )
        assert login_response.status_code == 200, login_response.text
        token = login_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create a chat session
        session_id_input = f"CHAT-test-{uuid4().hex}"
        create_response = await ac.post(
            "/api/v1/agent/chats",
            json={"id": session_id_input, "title": "New device judgment"},
            headers=headers,
        )
        assert create_response.status_code == 200, create_response.text
        session_id = create_response.json()["data"]["id"]
        assert create_response.json()["data"]["title"] == "New device judgment"

        # 3. Add a user message to the session
        msg1_id_input = f"MSG-user-{uuid4().hex}"
        msg1_response = await ac.post(
            f"/api/v1/agent/chats/{session_id}/messages",
            json={
                "id": msg1_id_input,
                "role": "user",
                "content": "My CGM device has a needle issue RVK19",
            },
            headers=headers,
        )
        assert msg1_response.status_code == 200, msg1_response.text
        msg1_id = msg1_response.json()["data"]["id"]

        # 4. Add an assistant message to the session
        msg2_id_input = f"MSG-assistant-{uuid4().hex}"
        msg2_response = await ac.post(
            f"/api/v1/agent/chats/{session_id}/messages",
            json={
                "id": msg2_id_input,
                "role": "assistant",
                "content": "We classified your issue as Application failure.",
                "options": [{"category": "Application failure", "title": "Applicator issue"}],
            },
            headers=headers,
        )
        assert msg2_response.status_code == 200, msg2_response.text
        msg2_id = msg2_response.json()["data"]["id"]

        # 5. Get the chat session details and verify title auto-update and messages list
        get_response = await ac.get(
            f"/api/v1/agent/chats/{session_id}",
            headers=headers,
        )
        assert get_response.status_code == 200, get_response.text
        data = get_response.json()["data"]
        # The title should have auto-updated to the first user message's content
        assert data["title"] == "My CGM device has a needle issue RVK19"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["id"] == msg1_id
        assert data["messages"][1]["id"] == msg2_id
        assert "insight" not in data["messages"][1] or data["messages"][1]["insight"] is None
        assert data["messages"][1]["options"][0]["category"] == "Application failure"

        # 6. List all chat sessions
        list_response = await ac.get(
            "/api/v1/agent/chats",
            headers=headers,
        )
        assert list_response.status_code == 200, list_response.text
        sessions = list_response.json()["data"]
        assert any(s["id"] == session_id for s in sessions)

        # 7. Update chat session title manually
        patch_response = await ac.patch(
            f"/api/v1/agent/chats/{session_id}",
            json={"title": "Updated Title Manual"},
            headers=headers,
        )
        assert patch_response.status_code == 200, patch_response.text
        assert patch_response.json()["data"]["title"] == "Updated Title Manual"

        # 8. Delete the chat session
        delete_response = await ac.delete(
            f"/api/v1/agent/chats/{session_id}",
            headers=headers,
        )
        assert delete_response.status_code == 200, delete_response.text
        assert delete_response.json()["data"] == {"success": True}

        # 9. Get deleted session should fail
        get_fail_response = await ac.get(
            f"/api/v1/agent/chats/{session_id}",
            headers=headers,
        )
        assert get_fail_response.status_code == 404
