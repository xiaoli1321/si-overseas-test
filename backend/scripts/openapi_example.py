"""Minimal partner flow. Set OPENAPI_BASE_URL, OPENAPI_EMAIL and OPENAPI_PASSWORD."""
import os
import time

import httpx


base_url = os.environ.get("OPENAPI_BASE_URL", "http://localhost:8000/openapi/v1")
credentials = {"email": os.environ["OPENAPI_EMAIL"], "password": os.environ["OPENAPI_PASSWORD"]}

with httpx.Client(timeout=30) as client:
    token = client.post(f"{base_url}/auth/login", json=credentials).json()["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "erp-case-20260710-001"}
    created = client.post(
        f"{base_url}/detections",
        headers=headers,
        json={"serialNo": "P2251212806JND44", "faultCategory": "Sensor Abnormal"},
    ).json()["data"]
    detection_id = created["detectionId"]
    while True:
        time.sleep(3)
        result = client.get(f"{base_url}/detections/{detection_id}", headers=headers).json()["data"]
        if result["status"] in {"completed", "failed"}:
            print(result)
            break
