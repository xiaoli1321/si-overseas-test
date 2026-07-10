import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_threshold_versioning_and_rollback() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Login
        login_response = await ac.post(
            "/api/v1/auth/login",
            json={"email": "christest@sibionics.com", "password": "password123"},
        )
        assert login_response.status_code == 200, login_response.text
        headers = {"Authorization": f"Bearer {login_response.json()['data']['access_token']}"}

        # 2. Get current active threshold
        curr_resp = await ac.get("/api/v1/thresholds/current", headers=headers)
        assert curr_resp.status_code == 200, curr_resp.text
        curr_data = curr_resp.json()["data"]
        initial_version = curr_data.get("version", 1)

        # 3. Get history before adding new ones
        hist_resp = await ac.get("/api/v1/thresholds/history", headers=headers)
        assert hist_resp.status_code == 200, hist_resp.text
        hist_data = hist_resp.json()["data"]
        assert len(hist_data) >= 1
        assert hist_data[0]["version"] == initial_version

        # 4. Save a new threshold (version = initial_version + 1)
        custom_config_1 = {
            "display": {"glucoseUnit": "mg/dL"},
            "rules": {
                "inaccuracy": {
                    "lowPersist": {"belowMmol": 2.8, "minHours": 4, "max24hMmol": 7.0},
                    "noFluctuation": {"floorMmol": 4.5, "minHours": 8, "maxSwingMmol": 1.0},
                    "jump": {"deltaMmol": 3.0, "consecutive": 3},
                    "deviation": {
                        "within48hDeviationMmol": 7.0,
                        "after48hDeviationRangePct": 20,
                        "after48hWearDays": 2,
                    },
                },
                "deviceAbnormal": {"wearDays": 0, "temporaryAbnormalHours": 3},
                "detachment": {"detachedStatusValue": 1, "wearDays": 14},
                "applicationFailure": {"afterSalesScore": 8, "manualReviewScore": 5},
            }
        }
        
        save_1_resp = await ac.post(
            "/api/v1/thresholds",
            json={**custom_config_1, "remark": "Initial test remark"},
            headers=headers,
        )
        assert save_1_resp.status_code == 200, save_1_resp.text
        save_1_data = save_1_resp.json()["data"]
        version_1 = save_1_data["version"]
        assert version_1 == initial_version + 1
        assert save_1_data["rules"]["inaccuracy"]["lowPersist"]["max24hMmol"] == 7.0
        assert save_1_data["rules"]["inaccuracy"]["deviation"]["within48hPairCount"] == 2
        assert save_1_data["rules"]["inaccuracy"]["deviation"]["within48hQualifiedPairCount"] == 2
        assert save_1_data["rules"]["inaccuracy"]["deviation"]["after48hPairCount"] == 2
        assert save_1_data["rules"]["inaccuracy"]["deviation"]["after48hQualifiedPairCount"] == 2
        assert save_1_data["rules"]["applicationFailure"]["photoCount"] == 2
        assert save_1_data["display"]["glucoseUnit"] == "mg/dL"
        assert save_1_data["remark"] == "Initial test remark"

        # 5. Save another threshold (version = initial_version + 2)
        custom_config_2 = {
            "rules": {
                "inaccuracy": {
                    "lowPersist": {"belowMmol": 2.8, "minHours": 4, "max24hMmol": 8.0},
                    "noFluctuation": {"floorMmol": 4.5, "minHours": 8, "maxSwingMmol": 1.0},
                    "jump": {"deltaMmol": 3.0, "consecutive": 3},
                    "deviation": {
                        "within48hDeviationMmol": 7.0,
                        "after48hDeviationRangePct": 20,
                        "after48hWearDays": 2,
                    },
                },
                "deviceAbnormal": {"wearDays": 0, "temporaryAbnormalHours": 3},
                "detachment": {"detachedStatusValue": 1, "wearDays": 14},
                "applicationFailure": {"afterSalesScore": 8, "manualReviewScore": 5},
            }
        }
        
        save_2_resp = await ac.post(
            "/api/v1/thresholds",
            json=custom_config_2,
            headers=headers,
        )
        assert save_2_resp.status_code == 200, save_2_resp.text
        save_2_data = save_2_resp.json()["data"]
        version_2 = save_2_data["version"]
        assert version_2 == initial_version + 2
        assert save_2_data["rules"]["inaccuracy"]["lowPersist"]["max24hMmol"] == 8.0
        assert save_2_data["remark"] is None

        # 6. Verify history contains all versions in descending order
        hist_resp = await ac.get("/api/v1/thresholds/history", headers=headers)
        assert hist_resp.status_code == 200, hist_resp.text
        hist_data = hist_resp.json()["data"]
        assert len(hist_data) >= 3
        assert hist_data[0]["version"] == version_2
        assert hist_data[1]["version"] == version_1
        assert hist_data[1]["remark"] == "Initial test remark"

        # 7. Rollback to version_1 (max24hMmol = 7.0) with custom remark
        rollback_resp = await ac.post(
            f"/api/v1/thresholds/rollback/{version_1}",
            json={"remark": "Rollback test remark"},
            headers=headers,
        )
        assert rollback_resp.status_code == 200, rollback_resp.text
        rollback_data = rollback_resp.json()["data"]
        # The new active version becomes version_2 + 1
        assert rollback_data["version"] == version_2 + 1
        assert rollback_data["rules"]["inaccuracy"]["lowPersist"]["max24hMmol"] == 7.0
        assert rollback_data["remark"] == "Rollback test remark"
        assert rollback_data["restoredFrom"] == version_1

        # 8. Verify the current active threshold is indeed the rolled-back version
        final_curr_resp = await ac.get("/api/v1/thresholds/current", headers=headers)
        assert final_curr_resp.status_code == 200, final_curr_resp.text
        final_curr_data = final_curr_resp.json()["data"]
        assert final_curr_data["version"] == version_2 + 1
        assert final_curr_data["remark"] == "Rollback test remark"
        assert final_curr_data["restoredFrom"] == version_1

        # 9. Update the remark of version_2
        update_remark_resp = await ac.put(
            f"/api/v1/thresholds/history/{version_2}/remark",
            json={"remark": "Updated remark for v2"},
            headers=headers,
        )
        assert update_remark_resp.status_code == 200, update_remark_resp.text
        assert update_remark_resp.json()["data"]["remark"] == "Updated remark for v2"

        # Verify in history
        hist_resp = await ac.get("/api/v1/thresholds/history", headers=headers)
        hist_data = hist_resp.json()["data"]
        v2_item = next(x for x in hist_data if x["version"] == version_2)
        assert v2_item["remark"] == "Updated remark for v2"

        # 10. Soft hide version_1
        delete_resp = await ac.delete(
            f"/api/v1/thresholds/history/{version_1}",
            headers=headers,
        )
        assert delete_resp.status_code == 200, delete_resp.text
        assert delete_resp.json()["data"]["isHidden"] is True

        # Verify version_1 is now hidden from the history response list
        hist_resp = await ac.get("/api/v1/thresholds/history", headers=headers)
        hist_data = hist_resp.json()["data"]
        assert not any(x["version"] == version_1 for x in hist_data)
