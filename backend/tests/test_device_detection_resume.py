import pytest

from src.integrations.mock_cgm import MockCGMClient
from src.schemas.domain import DeviceSearchRequest


def test_device_search_request_should_parse_multiline_and_deduplicate_terms() -> None:
    payload = DeviceSearchRequest(query="P2251212806JND44\njnd44, RVK19", serialNos=["RVK19", "P2251212813RVK19"])

    assert payload.search_terms() == ["P2251212806JND44", "jnd44", "RVK19", "P2251212813RVK19"]


@pytest.mark.asyncio
async def test_mock_cgm_search_device_terms_should_return_deduped_matches() -> None:
    client = MockCGMClient()

    matches = await client.search_device_terms(["P2251212806JND44", "JND44", "RVK19"])

    assert [device["sn"] for device in matches] == ["P2251212806JND44", "P2251212813RVK19"]
