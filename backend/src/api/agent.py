import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import get_current_user
from src.core.logging import log_context
from src.core.responses import ok
from src.models.tables import User
from src.schemas.domain import AgentClassifyRequest
from src.services.agent import classify_fault

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)


@router.post("/classify")
async def classify_endpoint(
    payload: AgentClassifyRequest, user: Annotated[User, Depends(get_current_user)]
) -> dict:
    result = await classify_fault(payload.message)
    data = result.model_dump()
    data["faultCategory"] = data.pop("fault_category")
    data["intentType"] = data.pop("intent_type")
    data["manualReview"] = data.pop("manual_review")
    data["fallbackUsed"] = data.pop("fallback_used")
    logger.info(
        "Agent classification endpoint completed",
        extra=log_context(
            "agent.classify_endpoint_completed",
            user_id=user.id,
            fault_category=result.fault_category,
            source=result.source,
            fallback_used=result.fallback_used,
        ),
    )
    return ok(data)
