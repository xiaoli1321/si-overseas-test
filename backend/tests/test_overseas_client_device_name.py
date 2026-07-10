"""
Tests for deviceName (Bluetooth name) query support.

Bluetooth names start with "AA" and are exactly 10 characters (e.g. AA250862SE).
One Bluetooth name may map to multiple devices, so queries by name return a list.
"""
import pytest
from unittest.mock import AsyncMock, patch

from src.core.exceptions import InvalidParamsError, NotFoundError
from src.integrations.overseas_client import (
    OverseasCGMClient,
    is_bluetooth_name,
    validate_bluetooth_name,
)
from src.integrations.mock_cgm import MockCGMClient
from src.core.config import get_settings


# ── Helper Functions ────────────────────────────────────────────


class TestIsBluetoothName:
    def test_aa_prefix_is_bluetooth_name(self) -> None:
        assert is_bluetooth_name("AA250862SE") is True

    def test_aa_lowercase_prefix_is_bluetooth_name(self) -> None:
        assert is_bluetooth_name("aa250862se") is True

    def test_sn_prefix_is_not_bluetooth_name(self) -> None:
        assert is_bluetooth_name("P2251212806JND44") is False

    def test_empty_string_is_not_bluetooth_name(self) -> None:
        assert is_bluetooth_name("") is False

    def test_other_prefix_is_not_bluetooth_name(self) -> None:
        assert is_bluetooth_name("BB250862SE") is False


class TestValidateBluetoothName:
    def test_valid_name_returns_uppercase(self) -> None:
        result = validate_bluetooth_name("aa250862se")
        assert result == "AA250862SE"

    def test_exact_10_char_name_accepted(self) -> None:
        result = validate_bluetooth_name("AA260901AB")
        assert result == "AA260901AB"

    def test_partial_name_raises_error(self) -> None:
        """Fuzzy/incomplete Bluetooth names are not allowed"""
        with pytest.raises(InvalidParamsError, match="complete Bluetooth name"):
            validate_bluetooth_name("AA25")

    def test_name_too_long_raises_error(self) -> None:
        with pytest.raises(InvalidParamsError, match="complete Bluetooth name"):
            validate_bluetooth_name("AA250862SE00")

    def test_name_with_special_chars_raises_error(self) -> None:
        with pytest.raises(InvalidParamsError, match="complete Bluetooth name"):
            validate_bluetooth_name("AA25086*SE")

    def test_non_aa_prefix_raises_error(self) -> None:
        with pytest.raises(InvalidParamsError):
            validate_bluetooth_name("BB250862SE")


# ── MockCGMClient Tests ─────────────────────────────────────────


class TestMockCGMClientBluetoothName:
    """
    Tests using MockCGMClient (offline, no real API).
    MOCK_DEVICES has AA250862SE mapped to two SNs and AA260901AB mapped to one SN.
    """

    @pytest.mark.asyncio
    async def test_get_device_by_bluetooth_name_returns_list(self) -> None:
        client = MockCGMClient()
        result = await client.get_device("AA250862SE")
        assert isinstance(result, list)
        assert len(result) == 2
        sns = {d["sn"] for d in result}
        assert "P2251212806JND44" in sns
        assert "P2251212814SWL27" in sns

    @pytest.mark.asyncio
    async def test_get_device_by_bluetooth_name_lowercase(self) -> None:
        """Case-insensitive lookup"""
        client = MockCGMClient()
        result = await client.get_device("aa250862se")
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_device_by_sn_returns_dict(self) -> None:
        client = MockCGMClient()
        result = await client.get_device("P2251212806JND44")
        assert isinstance(result, dict)
        assert result["sn"] == "P2251212806JND44"

    @pytest.mark.asyncio
    async def test_get_device_by_single_name_returns_list_with_one(self) -> None:
        client = MockCGMClient()
        result = await client.get_device("AA260901AB")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["sn"] == "P2251212807KPD52"

    @pytest.mark.asyncio
    async def test_get_device_by_invalid_bluetooth_name_raises(self) -> None:
        """Incomplete/fuzzy name raises InvalidParamsError"""
        client = MockCGMClient()
        with pytest.raises(InvalidParamsError):
            await client.get_device("AA25")

    @pytest.mark.asyncio
    async def test_get_device_by_unknown_bluetooth_name_raises_not_found(self) -> None:
        """Valid format but not in MOCK_DEVICES -> NotFoundError"""
        client = MockCGMClient()
        with pytest.raises(NotFoundError):
            await client.get_device("AA99999999")

    @pytest.mark.asyncio
    async def test_search_devices_by_bluetooth_name(self) -> None:
        client = MockCGMClient()
        result = await client.search_devices("AA250862SE")
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_search_device_terms_mixed_sn_and_bluetooth(self) -> None:
        """Hybrid batch: one SN + one Bluetooth name"""
        client = MockCGMClient()
        # P2251212807KPD52 is an SN; AA250862SE maps to 2 devices
        result = await client.search_device_terms(["P2251212807KPD52", "AA250862SE"])
        sns = {d["sn"] for d in result}
        assert "P2251212807KPD52" in sns
        assert "P2251212806JND44" in sns
        assert "P2251212814SWL27" in sns
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_search_device_terms_deduplication(self) -> None:
        """Same Bluetooth name twice -> deduplicated"""
        client = MockCGMClient()
        result = await client.search_device_terms(["AA250862SE", "AA250862SE"])
        assert len(result) == 2  # Not 4

    @pytest.mark.asyncio
    async def test_batch_get_devices_mixed_sn_and_bluetooth(self) -> None:
        client = MockCGMClient()
        result = await client.batch_get_devices(["P2251212807KPD52", "AA250862SE"])
        sns = {d["sn"] for d in result}
        assert len(sns) == 3  # 1 SN + 2 from Bluetooth name
        assert "P2251212807KPD52" in sns

    @pytest.mark.asyncio
    async def test_batch_get_devices_deduplication(self) -> None:
        """SN + Bluetooth name that includes that SN -> no duplicate"""
        client = MockCGMClient()
        result = await client.batch_get_devices(["AA250862SE", "P2251212806JND44"])
        sns = [d["sn"] for d in result]
        assert sns.count("P2251212806JND44") == 1

    @pytest.mark.asyncio
    async def test_get_devices_by_name_returns_adapted_tuples(self) -> None:
        """get_devices_by_name returns list of (device, glucose, alarm) tuples"""
        client = MockCGMClient()
        results = await client.get_devices_by_name("AA250862SE")
        assert len(results) == 2
        for device, glucose, alarm in results:
            assert "sn" in device
            assert "points" in glucose
            assert "latest_alarm_status" in alarm
            # Timestamps should be ISO strings, not datetime objects
            for point in glucose["points"]:
                assert isinstance(point["timestamp"], str)
            assert isinstance(alarm["latest_sensor_alert"], str)


# ── OverseasCGMClient Tests (mocked HTTP) ──────────────────────


class TestOverseasCGMClientBluetoothName:
    """
    Tests for OverseasCGMClient with mocked HTTP responses.
    """

    def _make_client(self) -> OverseasCGMClient:
        settings = get_settings()
        return OverseasCGMClient(settings)

    @pytest.mark.asyncio
    async def test_get_device_by_sn_returns_dict(self) -> None:
        client = self._make_client()

        fake_detail = {
            "serialNo": "TESGS1ASTEST01",
            "deviceName": "AA250862SE",
            "enableTime": "1723805564000.000000",
            "status": 1,
            "wearDurationHours": 12.0,
            "fallOffStatus": "未脱落",
            "glucoseInfo": [],
        }
        with patch.object(client, "_fetch_device_detail", AsyncMock(return_value=fake_detail)):
            result = await client.get_device("TESGS1ASTEST01")
        assert isinstance(result, dict)
        assert result["sn"] == "TESGS1ASTEST01"

    @pytest.mark.asyncio
    async def test_get_device_by_bluetooth_name_returns_list(self) -> None:
        client = self._make_client()

        fake_list = [
            {
                "serialNo": "SN_BT_DEVICE1",
                "deviceName": "AA250862SE",
                "enableTime": "1723805564000.000000",
                "status": 1,
                "wearDurationHours": 12.0,
                "fallOffStatus": "未脱落",
                "glucoseInfo": [],
            },
            {
                "serialNo": "SN_BT_DEVICE2",
                "deviceName": "AA250862SE",
                "enableTime": "1723805564000.000000",
                "status": 1,
                "wearDurationHours": 6.0,
                "fallOffStatus": "未脱落",
                "glucoseInfo": [],
            },
        ]
        with patch.object(client, "_fetch_device_detail_by_name", AsyncMock(return_value=fake_list)):
            result = await client.get_device("AA250862SE")
        assert isinstance(result, list)
        assert len(result) == 2
        sns = {d["sn"] for d in result}
        assert sns == {"AA250862SE"}

    @pytest.mark.asyncio
    async def test_get_device_by_invalid_bluetooth_name_raises(self) -> None:
        client = self._make_client()
        with pytest.raises(InvalidParamsError):
            await client.get_device("AA250")  # Too short

    @pytest.mark.asyncio
    async def test_glucose_and_alarm_by_single_bluetooth_name(self) -> None:
        client = self._make_client()
        glucose = {"points": [{"glucose": 5.6}]}
        alarm = {"latest_alarm_status": 2}

        with patch.object(
            client,
            "_get_adapted_data_by_device_name",
            AsyncMock(return_value=[({"sn": "AA260901AB"}, glucose, alarm)]),
        ) as by_name:
            assert await client.get_glucose_series("AA260901AB") is glucose
            assert await client.get_latest_alarm("AA260901AB") is alarm

        assert by_name.await_count == 2

    @pytest.mark.asyncio
    async def test_glucose_by_ambiguous_bluetooth_name_requires_serial_no(self) -> None:
        client = self._make_client()

        with patch.object(
            client,
            "_get_adapted_data_by_device_name",
            AsyncMock(
                return_value=[
                    ({"sn": "SN-1"}, {"points": []}, {}),
                    ({"sn": "SN-2"}, {"points": []}, {}),
                ]
            ),
        ):
            with pytest.raises(InvalidParamsError, match="submit serialNo"):
                await client.get_glucose_series("AA250862SE")

    @pytest.mark.asyncio
    async def test_search_device_terms_mixed(self) -> None:
        client = self._make_client()

        fake_sn_detail = {
            "serialNo": "TESGS1ASTEST01",
            "deviceName": "AA250862SE",
            "enableTime": "1723805564000.000000",
            "status": 1,
            "wearDurationHours": 12.0,
            "fallOffStatus": "未脱落",
            "glucoseInfo": [],
        }
        fake_bt_list = [
            {
                "serialNo": "SN_BT_DEVICE1",
                "deviceName": "AA250862SE",
                "enableTime": "1723805564000.000000",
                "status": 1,
                "wearDurationHours": 6.0,
                "fallOffStatus": "未脱落",
                "glucoseInfo": [],
            },
        ]

        with (
            patch.object(client, "_fetch_device_detail", AsyncMock(return_value=fake_sn_detail)),
            patch.object(client, "_fetch_device_detail_by_name", AsyncMock(return_value=fake_bt_list)),
        ):
            result = await client.search_device_terms(["TESGS1ASTEST01", "AA250862SE"])

        sns = {d["sn"] for d in result}
        assert "TESGS1ASTEST01" in sns
        assert "AA250862SE" in sns
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_search_device_terms_deduplication(self) -> None:
        """Same Bluetooth name -> deduplicated"""
        client = self._make_client()

        fake_sn_detail = {
            "serialNo": "SN_BT_DEVICE1",
            "deviceName": "AA250862SE",
            "enableTime": "1723805564000.000000",
            "status": 1,
            "wearDurationHours": 6.0,
            "fallOffStatus": "未脱落",
            "glucoseInfo": [],
        }
        fake_bt_list = [
            {
                "serialNo": "SN_BT_DEVICE1",
                "deviceName": "AA250862SE",
                "enableTime": "1723805564000.000000",
                "status": 1,
                "wearDurationHours": 6.0,
                "fallOffStatus": "未脱落",
                "glucoseInfo": [],
            },
        ]

        with (
            patch.object(client, "_fetch_device_detail", AsyncMock(return_value=fake_sn_detail)),
            patch.object(client, "_fetch_device_detail_by_name", AsyncMock(return_value=fake_bt_list)),
        ):
            result = await client.search_device_terms(["AA250862SE", "AA250862SE"])

        assert len(result) == 1
        assert result[0]["sn"] == "AA250862SE"

    @pytest.mark.asyncio
    async def test_bluetooth_name_fallback_to_mock(self) -> None:
        """When real API fails for Bluetooth name query, fallback to MockCGMClient"""
        client = self._make_client()

        with patch.object(
            client,
            "_fetch_device_detail_by_name",
            side_effect=Exception("API unavailable"),
        ):
            # AA250862SE is in MOCK_DEVICES with 2 devices
            result = await client.get_device("AA250862SE")

        assert isinstance(result, list)
        assert len(result) == 2
