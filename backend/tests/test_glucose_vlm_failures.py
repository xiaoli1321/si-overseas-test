from types import SimpleNamespace

import pytest

from src.integrations.vlm import QwenVlClient, VlmRequestError


@pytest.mark.asyncio
async def test_live_glucose_timeout_does_not_return_fabricated_readings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        vlm_model="qwen-test",
        vlm_max_retries=2,
        vlm_request_timeout_seconds=3.0,
    )
    client = QwenVlClient(settings=settings)
    monkeypatch.setattr(client, "_can_call_live_model", lambda _: True)

    def timeout(_: list[str]):
        raise TimeoutError("request exceeded 3 seconds")

    monkeypatch.setattr(client, "_call_live_glucose_model", timeout)

    with pytest.raises(VlmRequestError, match="TimeoutError"):
        await client.analyze_glucose_readings(["data:image/jpeg;base64,abc"])
