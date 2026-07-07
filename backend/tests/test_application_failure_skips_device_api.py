"""植入失败 (Application failure) 场景跳过设备接口查询的回归测试。

背景：植入失败的设备通常尚未激活，海外设备接口查询不到（返回为空）。
因此该场景不应再调用设备接口，而是直接信任用户输入的 SN / deviceName，
仅走图片上传 + 图片识别的流程。
"""

import io

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.core.database import engine
from src.services.detections import _unactivated_device_inputs


def test_unactivated_device_inputs_trusts_user_input_without_api() -> None:
    from src.core.config import get_settings

    device, glucose, alarm = _unactivated_device_inputs("AA250862SE")

    # 直接采用用户输入，未查询设备接口
    assert device["sn"] == "AA250862SE"
    assert device["status"] == "not_activated"
    assert device["device_status"] == 0
    assert device["device_type"] == get_settings().default_device_type
    # 植入失败仅依赖图片，血糖 / 告警为占位空数据
    assert glucose["points"] == []
    assert alarm["abnormal_duration_minutes"] == 0


@pytest.mark.asyncio
async def test_application_failure_detection_never_calls_device_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import get_settings
    import src.services.detections as detections

    settings = get_settings()
    monkeypatch.setattr(settings, "vlm_enabled", False)
    # 关闭 dashscope，让 VLM 与植入失败扫描器走离线兜底，避免真实网络调用
    monkeypatch.setattr(settings, "dashscope_api_key", "")

    # 植入失败场景绝不应调用设备接口：一旦被调用即视为回归
    def _fail_if_called() -> None:
        raise AssertionError(
            "get_cgm_client must not be called for Application failure detections"
        )

    monkeypatch.setattr(detections, "get_cgm_client", _fail_if_called)

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            login = await ac.post(
                "/api/v1/auth/login",
                json={"email": "christest@sibionics.com", "password": "password123"},
            )
            assert login.status_code == 200, login.text
            headers = {
                "Authorization": f"Bearer {login.json()['data']['access_token']}"
            }

            upload = await ac.post(
                "/api/v1/files/upload",
                files={"file": ("impl.png", io.BytesIO(b"fake image bytes"), "image/png")},
                headers=headers,
            )
            assert upload.status_code == 200, upload.text
            file_id = upload.json()["data"]["id"]

            # 未激活设备，使用蓝牙名 (deviceName) 作为标识
            serial_no = "AA250862SE"
            create = await ac.post(
                "/api/v1/detections",
                json={
                    "serialNo": serial_no,
                    "faultCategory": "Application failure",
                    "fileIds": [file_id],
                },
                headers=headers,
            )
            assert create.status_code == 200, create.text
            record_id = create.json()["data"]["id"]

            detail = await ac.get(
                f"/api/v1/detections/{record_id}", headers=headers
            )
            assert detail.status_code == 200, detail.text
            data = detail.json()["data"]

            # 即便设备接口不可用，植入失败诊断也应成功跑完（不落入 failed）
            assert data["status"] == "complete", data
            device_snap = data["evidence"]["device"]
            assert device_snap["sn"] == serial_no
            assert device_snap["status"] == "not_activated"
    finally:
        await engine.dispose()
