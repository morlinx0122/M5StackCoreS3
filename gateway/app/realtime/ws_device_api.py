from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.realtime_session import RealtimeVoiceSession
from app.realtime.realtime_trace import mark

router = APIRouter()


@router.websocket("/ws/device/{device_id}")
async def ws_device(websocket: WebSocket, device_id: str):
    await websocket.accept()
    session = RealtimeVoiceSession(websocket, device_id)
    await session.start()
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                mark(session.session_id, "disconnected")
                break
            if "text" in message and message["text"] is not None:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    await session.send_json({"type": "error", "error_code": "INVALID_JSON"})
                    continue
                await session.handle_json(payload)
            elif "bytes" in message and message["bytes"] is not None:
                await session.handle_audio_frame(message["bytes"])
    except WebSocketDisconnect:
        mark(session.session_id, "disconnected")
    except Exception as exc:
        mark(session.session_id, "failed", error_code=exc.__class__.__name__, error_message=str(exc))
        raise
