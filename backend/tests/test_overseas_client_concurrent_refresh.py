import asyncio
import time
from typing import Any

import httpx
import pytest

from src.core.config import get_settings
from src.integrations.overseas_client import OverseasCGMClient


class ConcurrentFakeAsyncClient:
    def __init__(
        self,
        *,
        login_counter: list[int],
        captured_requests: list[dict[str, Any]],
        **_: Any,
    ) -> None:
        self._login_counter = login_counter
        self._captured_requests = captured_requests

    async def __aenter__(self) -> "ConcurrentFakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> httpx.Response:
        self._captured_requests.append({"method": "POST", "url": url, "json": json})
        await asyncio.sleep(0.05)  # Yield control to simulate network latency
        req = httpx.Request("POST", url, json=json)
        if "login" in url:
            self._login_counter[0] += 1
            token = f"fresh-token-{self._login_counter[0]}"
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "access_token": token,
                        "expires_in": 1209600,
                    },
                },
                request=req,
            )
        return httpx.Response(404, json={"code": 404, "msg": "Not found"}, request=req)

    async def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> httpx.Response:
        auth_header = headers.get("Authorization", "")
        token = auth_header.split("Bearer ")[-1] if "Bearer " in auth_header else ""
        
        self._captured_requests.append({
            "method": "GET",
            "url": url,
            "params": params,
            "token": token,
        })
        
        await asyncio.sleep(0.05)  # Yield control to simulate network latency
        req = httpx.Request("GET", url, params=params, headers=headers)
        
        if token == "expired-token":
            return httpx.Response(401, json={"code": 401, "msg": "Login state has expired"}, request=req)
        
        sn = params.get("sn", "UNKNOWN")
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": [
                    {
                        "sn": sn,
                        "status": 1,
                    }
                ],
            },
            request=req,
        )


@pytest.mark.asyncio
async def test_overseas_client_concurrent_token_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    client = OverseasCGMClient(settings)

    # Initialize the client with an expired token that the client currently believes is valid
    client._token = "expired-token"
    client._token_expires_at = time.time() + 3600.0  # valid locally, but expired on server

    login_counter = [0]
    captured_requests = []

    monkeypatch.setattr(
        "src.integrations.overseas_client.httpx.AsyncClient",
        lambda **kwargs: ConcurrentFakeAsyncClient(
            login_counter=login_counter,
            captured_requests=captured_requests,
            **kwargs,
        ),
    )

    # Trigger 5 concurrent device detail requests
    tasks = [
        client.get_device("SN-1"),
        client.get_device("SN-2"),
        client.get_device("SN-3"),
        client.get_device("SN-4"),
        client.get_device("SN-5"),
    ]

    results = await asyncio.gather(*tasks)

    # Verify that all 5 device queries completed successfully
    assert len(results) == 5
    for i, res in enumerate(results):
        assert res["sn"] == f"SN-{i+1}"
        assert res["status"] == "wearing"

    # Verify that only a single login was performed
    assert login_counter[0] == 1

    # Verify requests breakdown
    get_requests = [req for req in captured_requests if req["method"] == "GET"]
    post_requests = [req for req in captured_requests if req["method"] == "POST"]

    assert len(post_requests) == 1
    
    # There should be 10 GET requests total: 5 initial ones with expired-token, and 5 retried ones with fresh-token-1
    assert len(get_requests) == 10
    
    expired_get_reqs = [r for r in get_requests if r["token"] == "expired-token"]
    fresh_get_reqs = [r for r in get_requests if r["token"] == "fresh-token-1"]
    
    assert len(expired_get_reqs) == 5
    assert len(fresh_get_reqs) == 5
