from typing import Any


def ok(data: Any = None) -> dict[str, Any]:
    return {"code": 0, "message": "success", "data": data}
