import asyncio

import pytest

from src.core.exceptions import NotFoundError
from src.services.detections import _load_cgm_inputs


class BarrierCGMClient:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.all_started = asyncio.Event()

    async def _wait_until_all_started(self, name: str, value: dict) -> dict:
        self.started.append(name)
        if len(self.started) == 3:
            self.all_started.set()
        await self.all_started.wait()
        return value

    async def get_device(self, serial_no: str) -> dict:
        return await self._wait_until_all_started(
            "device",
            {"serial_no": serial_no, "device_type": "GS1"},
        )

    async def get_glucose_series(self, serial_no: str) -> dict:
        return await self._wait_until_all_started(
            "glucose",
            {"serial_no": serial_no, "points": []},
        )

    async def get_latest_alarm(self, serial_no: str) -> dict:
        return await self._wait_until_all_started(
            "alarm",
            {"serial_no": serial_no, "alarm": None},
        )


@pytest.mark.asyncio
async def test_load_cgm_inputs_should_query_external_sources_concurrently() -> None:
    client = BarrierCGMClient()

    device, glucose, alarm = await asyncio.wait_for(
        _load_cgm_inputs(client, "SN-001"),
        timeout=0.2,
    )

    assert sorted(client.started) == ["alarm", "device", "glucose"]
    assert device["serial_no"] == "SN-001"
    assert glucose["points"] == []
    assert alarm["alarm"] is None


@pytest.mark.asyncio
async def test_load_cgm_inputs_should_reject_empty_device_matches() -> None:
    class EmptyDeviceClient(BarrierCGMClient):
        async def get_device(self, serial_no: str) -> list:
            return await self._wait_until_all_started("device", [])

    with pytest.raises(NotFoundError):
        await asyncio.wait_for(
            _load_cgm_inputs(EmptyDeviceClient(), "SN-404"),
            timeout=0.2,
        )
