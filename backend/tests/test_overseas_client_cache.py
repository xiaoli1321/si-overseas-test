import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import get_settings
from src.core.exceptions import NotFoundError
from src.integrations.overseas_client import OverseasCGMClient


def _make_client(**overrides) -> OverseasCGMClient:
    settings = get_settings().model_copy(
        update={
            "overseas_api_cache_ttl_seconds": 300,
            "overseas_api_negative_cache_ttl_seconds": 60,
            "overseas_api_search_concurrency": 5,
            "overseas_api_request_timeout_seconds": 15.0,
            **overrides,
        }
    )
    return OverseasCGMClient(settings)


def _adapted(raw: dict, key: str, settings) -> tuple[dict, dict, dict]:
    return {"sn": key, "raw": raw}, {"points": []}, {"latest_alarm_status": 0}


@pytest.mark.asyncio
async def test_get_device_should_share_concurrent_fetch_for_same_sn() -> None:
    client = _make_client()
    call_count = 0

    async def fake_fetch(serial_no: str) -> dict:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        return {"serialNo": serial_no}

    with (
        patch.object(client, "_fetch_device_detail", side_effect=fake_fetch),
        patch(
            "src.integrations.overseas_client.adapt_device_detail",
            side_effect=_adapted,
        ),
    ):
        results = await asyncio.gather(
            *[client.get_device("SN-CACHE-001") for _ in range(5)]
        )

    assert call_count == 1
    assert [result["sn"] for result in results] == ["SN-CACHE-001"] * 5


@pytest.mark.asyncio
async def test_get_device_should_share_concurrent_fetch_for_same_device_name() -> None:
    client = _make_client()

    async def fake_fetch(device_name: str) -> list[dict]:
        await asyncio.sleep(0.01)
        return [{"deviceName": device_name}]

    fetch = AsyncMock(side_effect=fake_fetch)

    with (
        patch.object(client, "_fetch_device_detail_by_name", fetch),
        patch(
            "src.integrations.overseas_client.adapt_device_detail",
            side_effect=_adapted,
        ),
    ):
        results = await asyncio.gather(
            *[client.get_device("AA250862SE") for _ in range(5)]
        )

    assert fetch.await_count == 1
    assert all(result[0]["sn"] == "AA250862SE" for result in results)


@pytest.mark.asyncio
async def test_get_device_should_use_success_cache_until_ttl_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client(overseas_api_cache_ttl_seconds=10)
    now = [100.0]
    fetch = AsyncMock(return_value={"serialNo": "SN-TTL"})

    monkeypatch.setattr(
        "src.integrations.overseas_client.time.monotonic", lambda: now[0]
    )

    with (
        patch.object(client, "_fetch_device_detail", fetch),
        patch(
            "src.integrations.overseas_client.adapt_device_detail",
            side_effect=_adapted,
        ),
    ):
        await client.get_device("SN-TTL")
        await client.get_device("SN-TTL")
        now[0] += 11.0
        await client.get_device("SN-TTL")

    assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_search_devices_should_negative_cache_not_found_until_ttl_expires() -> None:
    client = _make_client(overseas_api_negative_cache_ttl_seconds=60)
    fetch = AsyncMock(side_effect=NotFoundError("Device not found"))

    with (
        patch.object(client, "_fetch_device_detail", fetch),
        patch(
            "src.integrations.mock_cgm.MockCGMClient.get_device",
            AsyncMock(side_effect=NotFoundError("Device not found")),
        ),
    ):
        first = await client.search_devices("SN-NOT-FOUND")
        second = await client.search_devices("SN-NOT-FOUND")

    assert first == []
    assert second == []
    assert fetch.await_count == 1
