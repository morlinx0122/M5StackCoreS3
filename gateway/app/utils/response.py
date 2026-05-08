import uuid
from typing import Any

from fastapi import Request


def request_id_from(request: Request) -> str:
    return request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex}"


def ok(request: Request, data: Any = None) -> dict[str, Any]:
    return {
        "code": "00000",
        "msg": "ok",
        "request_id": request_id_from(request),
        "data": data if data is not None else {},
    }

