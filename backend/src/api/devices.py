from typing import Annotated

from fastapi import APIRouter, Depends, Query
from src.api.deps import get_current_user
from src.core.responses import ok
from src.integrations import get_cgm_client
from src.models.tables import User
from src.schemas.domain import DeviceSearchRequest
from src.schemas.frontend import device_to_frontend


class CGMClientProxy:
    def __getattr__(self, name):
        return getattr(get_cgm_client(), name)


router = APIRouter(prefix="/devices", tags=["devices"])
client = CGMClientProxy()


@router.post("/search")
async def search_devices_post(
    payload: DeviceSearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    return ok(
        [
            device_to_frontend(device)
            for device in await client.search_device_terms(payload.search_terms())
        ]
    )


@router.get("/search/")
async def search_devices(
    current_user: Annotated[User, Depends(get_current_user)],
    keyword: str = Query(min_length=1),
) -> dict:
    return ok(
        [device_to_frontend(device) for device in await client.search_devices(keyword)]
    )


@router.get("/{serial_no}")
async def get_device(
    serial_no: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    result = await client.get_device(serial_no)
    # 蓝牙名称查询返回 list（一个名称可能对应多台设备）
    if isinstance(result, list):
        return ok([device_to_frontend(d) for d in result])
    return ok(device_to_frontend(result))


@router.post("/batch-query")
async def batch_query_devices(
    serial_nos: list[str],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    return ok(
        [
            device_to_frontend(device)
            for device in await client.batch_get_devices(serial_nos)
        ]
    )
