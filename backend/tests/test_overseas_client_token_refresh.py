from typing import Any

import httpx
import pytest

from src.core.config import get_settings
from src.integrations.overseas_client import OverseasCGMClient


class _FakeAsyncClient:
    def __init__(
        self,
        *,
        responses: list[httpx.Response],
        captured_headers: list[dict[str, str]],
        **_: Any,
    ) -> None:
        self._responses = responses
        self._captured_headers = captured_headers

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> httpx.Response:
        self._captured_headers.append(headers)
        response = self._responses.pop(0)
        return httpx.Response(
            response.status_code,
            json=response.json(),
            request=httpx.Request("GET", url, params=params, headers=headers),
        )


@pytest.mark.asyncio
async def test_overseas_client_should_refresh_token_on_http_401(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    client = OverseasCGMClient(settings)

    issued_tokens = iter(["expired-token", "fresh-token"])
    captured_headers: list[dict[str, str]] = []
    responses = [
        httpx.Response(401, json={"code": 401, "msg": "token expired"}),
        httpx.Response(200, json={"code": 200, "data": [{"sn": "SN-401", "deviceStatus": "active"}]}),
    ]

    async def fake_ensure_token() -> str:
        return next(issued_tokens)

    monkeypatch.setattr(client, "_ensure_token", fake_ensure_token)
    monkeypatch.setattr(
        "src.integrations.overseas_client.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(
            responses=responses,
            captured_headers=captured_headers,
            **kwargs,
        ),
    )

    detail = await client._fetch_device_detail("SN-401")

    assert detail == {"sn": "SN-401", "deviceStatus": "active"}
    assert captured_headers == [
        {"Authorization": "Bearer expired-token"},
        {"Authorization": "Bearer fresh-token"},
    ]
