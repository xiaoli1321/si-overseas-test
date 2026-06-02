import pytest
from unittest.mock import patch
from src.core.config import get_settings
from src.integrations.overseas_client import OverseasCGMClient

@pytest.mark.asyncio
async def test_overseas_client_fallback_to_mock() -> None:
    settings = get_settings()
    client = OverseasCGMClient(settings)
    
    # We choose one of the predefined mock serial numbers
    mock_sn = "P2251212806JND44"
    
    # Mock self._fetch_device_detail to raise an exception simulating live API failure/not found
    with patch.object(client, "_fetch_device_detail", side_effect=Exception("Simulated live API error")):
        device, glucose, alarm = await client._get_adapted_data(mock_sn)
        
        # Verify that fallback succeeded and returned mock device data
        assert device is not None
        assert device["sn"] == mock_sn
        assert device["status"] == "abnormal"
        assert device["wearDays"] == 6
        
        # Verify glucose series
        assert glucose is not None
        assert "points" in glucose
        assert len(glucose["points"]) > 0
        for p in glucose["points"]:
            assert isinstance(p["timestamp"], str)  # Check that datetime was formatted to ISO string
            assert "glucose" in p
            assert "alarm_status" in p
            
        # Verify alarm
        assert alarm is not None
        assert "latest_alarm_status" in alarm
        assert "abnormal_duration_minutes" in alarm
        assert "latest_sensor_alert" in alarm
        assert isinstance(alarm["latest_sensor_alert"], str)  # Check that datetime was formatted to ISO string
