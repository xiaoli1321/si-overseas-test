from fastapi.testclient import TestClient

from src.main import app


def test_health_should_use_standard_envelope() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"code": 0, "message": "success", "data": {"status": "ok"}}


def test_openapi_should_expose_core_mvp_routes() -> None:
    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    expected = {
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/auth/users",
        "/api/v1/analytics/events",
        "/api/v1/analytics/summary",
        "/api/v1/devices/search",
        "/api/v1/detections",
        "/api/v1/detections/{record_id}",
        "/api/v1/detections/batch",
        "/api/v1/thresholds/current",
        "/api/v1/thresholds",
        "/api/v1/records",
        "/api/v1/records/stats",
        "/api/v1/batch-tasks/{task_id}",
    }
    assert expected.issubset(paths.keys())
