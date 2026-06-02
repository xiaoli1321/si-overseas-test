import asyncio
import json
import logging
import time
from typing import Any

from src.core.config import get_settings
from src.core.logging import current_millis, log_context
from src.schemas.domain import AgentClassifyResponse

logger = logging.getLogger(__name__)


async def classify_fault(message: str) -> AgentClassifyResponse:
    settings = get_settings()
    started = time.perf_counter()
    logger.info(
        "Intent classification started",
        extra=log_context(
            "agent.intent_started",
            message_length=len(message),
            vlm_enabled=settings.vlm_enabled,
            api_key_configured=bool(settings.dashscope_api_key),
        ),
    )

    if settings.dashscope_api_key and settings.vlm_enabled:
        try:
            # Run in a thread pool since openai client is synchronous
            result = await asyncio.to_thread(_call_llm_classify, message, settings)
            if result:
                logger.info(
                    "Intent classification completed with LLM",
                    extra=log_context(
                        "agent.intent_completed",
                        duration_ms=current_millis(started),
                        fault_category=result.fault_category,
                        source=result.source,
                        fallback_used=result.fallback_used,
                    ),
                )
                return result
        except Exception as exc:
            logger.error(
                "Intent classification LLM failed; falling back to keywords",
                extra=log_context(
                    "agent.intent_llm_failed",
                    error_type=type(exc).__name__,
                ),
                exc_info=True,
            )
    else:
        logger.info(
            "Intent classification using keyword fallback directly",
            extra=log_context(
                "agent.intent_llm_skipped",
                vlm_enabled=settings.vlm_enabled,
                api_key_configured=bool(settings.dashscope_api_key),
            ),
        )

    # Fallback to keyword matching
    normalized = message.lower()
    for category, words in settings.agent_keywords.items():
        if any(word in normalized for word in words.split()):
            logger.info(
                "Intent classification completed with keyword fallback",
                extra=log_context(
                    "agent.intent_completed",
                    duration_ms=current_millis(started),
                    fault_category=category,
                    source="keyword_fallback",
                    fallback_used=True,
                ),
            )
            return AgentClassifyResponse(
                fault_category=category,  # type: ignore[arg-type]
                intent_type="fault_category",
                confidence=0.75,
                message=f"According to our AIAgent's judgment, the type of device failure currently encountered by users may be [{category.lower()}], and you can click to enter the after-sales tool.",
                manual_review=False,
                source="keyword_fallback",
                fallback_used=True,
            )

    logger.info(
        "Intent classification completed with manual review",
        extra=log_context(
            "agent.intent_completed",
            duration_ms=current_millis(started),
            source="keyword_fallback",
            fallback_used=True,
            manual_review=True,
        ),
    )
    return AgentClassifyResponse(
        fault_category=None,
        intent_type="unknown",
        confidence=0.2,
        message="According to our AIAgent's judgment, the system cannot solve the current user's fault type for the time being, please make a manual judgment.",
        manual_review=True,
        source="keyword_fallback",
        fallback_used=True,
    )


def _call_llm_classify(message: str, settings: Any) -> AgentClassifyResponse | None:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from pydantic import BaseModel, Field
    from typing import Literal

    # Define the 6 categories for LLM classification
    LLMFaultCategory = Literal[
        "Data accuracy",
        "Sensor falling off",
        "Sensor Abnormal",
        "Application failure",
        "other_cgm",
        "unrelated",
    ]

    class LLMClassifyResult(BaseModel):
        fault_category: LLMFaultCategory = Field(
            description="The category of device failure."
        )

    logger.info(
        "Intent classification LLM request started",
        extra=log_context("agent.intent_llm_started", model=settings.intent_model),
    )

    llm = ChatOpenAI(
        model=settings.intent_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.vlm_base_url,
        temperature=0.1,
        timeout=15.0,
    )

    # Use method="json_mode" for robust compatibility with Dashscope
    structured_llm = llm.with_structured_output(LLMClassifyResult, method="json_mode")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", settings.agent_system_prompt),
            ("user", "{input}"),
        ]
    )

    chain = prompt | structured_llm
    result = chain.invoke({"input": message})
    category = result.fault_category
    logger.info(
        "Intent classification LLM returned category",
        extra=log_context("agent.intent_llm_category", fault_category=category),
    )

    if category in [
        "Data accuracy",
        "Sensor falling off",
        "Sensor Abnormal",
        "Application failure",
    ]:
        return AgentClassifyResponse(
            fault_category=category,  # type: ignore[arg-type]
            intent_type="fault_category",
            confidence=0.9,
            message=f"According to our AIAgent's judgment, the type of device failure currently encountered by users may be [{category.lower()}], and you can click to enter the after-sales tool.",
            manual_review=False,
            source="langchain",
            fallback_used=False,
        )
    elif category == "other_cgm":
        return AgentClassifyResponse(
            fault_category=None,
            intent_type="other_cgm",
            confidence=0.7,
            message="According to our AIAgent's judgment, the system cannot solve the current user's fault type for the time being, please make a manual judgment.",
            manual_review=True,
            source="langchain",
            fallback_used=False,
        )
    else:  # unrelated
        return AgentClassifyResponse(
            fault_category=None,
            intent_type="unrelated",
            confidence=0.7,
            message="Sorry, the issue you describe now is not related to CGM for the time being, please redescribe or consult something related to CGM failure.",
            manual_review=True,
            source="langchain",
            fallback_used=False,
        )
