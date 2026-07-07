from unittest.mock import MagicMock, patch

import pytest
from src.services.agent import classify_fault


@pytest.mark.asyncio
@patch("src.services.agent.get_settings")
async def test_classify_fault_fallback_keywords(mock_get_settings: MagicMock) -> None:
    settings_mock = MagicMock()
    settings_mock.dashscope_api_key = ""
    settings_mock.vlm_enabled = False
    settings_mock.agent_keywords = {
        "Application failure": "assembly needle launch electrode applicator insert photo",
        "Sensor falling off": "fall off detached loose peel fell",
        "Sensor Abnormal": "abnormal error warm-up warmup replace device recovery",
        "Data accuracy": "accuracy inaccurate bgm low fluctuation jump glucose",
    }
    mock_get_settings.return_value = settings_mock

    # 1. Test Chinese message with no LLM (fallback)
    res = await classify_fault("数据异常")
    assert res.fault_category is None
    assert res.manual_review is True

    # 2. Test English message matching keyword (fallback)
    res_en = await classify_fault("My sensor fell off during wear")
    assert res_en.fault_category == "Sensor falling off"
    assert res_en.confidence == 0.75
    assert res_en.manual_review is False
    assert res_en.source == "keyword_fallback"
    assert res_en.fallback_used is True


@pytest.mark.asyncio
@patch("src.services.agent.get_settings")
@patch("langchain_openai.ChatOpenAI")
async def test_classify_fault_with_llm(mock_chat_openai: MagicMock, mock_get_settings: MagicMock) -> None:
    # Mock settings
    settings_mock = MagicMock()
    settings_mock.dashscope_api_key = "test-key"
    settings_mock.vlm_enabled = True
    settings_mock.vlm_base_url = "https://test.url"
    settings_mock.intent_model = "test-model"
    settings_mock.agent_system_prompt = (
        "You are a professional quality assurance assistant for Continuous Glucose Monitoring (CGM) devices.\n"
        "Classify the user's issue description into one of the following categories:\n"
        "- \"Data accuracy\"\n"
        "- \"Sensor falling off\"\n"
        "- \"Sensor Abnormal\"\n"
        "- \"Application failure\"\n"
        "- \"other_cgm\"\n"
        "- \"unrelated\""
    )
    mock_get_settings.return_value = settings_mock

    # Mock client and response
    mock_llm = MagicMock()
    mock_chat_openai.return_value = mock_llm

    mock_structured_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm

    from types import SimpleNamespace
    mock_result = SimpleNamespace(
        fault_category="Sensor Abnormal"
    )
    mock_structured_llm.invoke.return_value = mock_result
    mock_structured_llm.return_value = mock_result

    res = await classify_fault("My sensor warm up error")
    assert res.fault_category == "Sensor Abnormal"
    assert res.message == "According to our AIAgent's judgment, the type of device failure currently encountered by users may be [sensor abnormal], and you can click to enter the after-sales tool."
    assert res.confidence == 0.9
    assert res.manual_review is False
    assert res.source == "langchain"
    assert res.fallback_used is False
