from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.device_service import enqueue_device_command


@dataclass(frozen=True)
class DeviceCommand:
    command_id: str
    row_id: int


def enqueue_play_audio(
    device_id: str,
    job_id: str,
    audio_url: str,
    text: str,
    emotion: str = "neutral",
    face_state: str = "SPEAKING",
) -> DeviceCommand:
    command_id, row_id = enqueue_device_command(
        device_id,
        "play_audio",
        {
            "type": "play_audio",
            "job_id": job_id,
            "audio_url": audio_url,
            "url": audio_url,
            "text": text,
            "emotion": emotion,
            "face_state": face_state,
        },
        job_id=job_id,
        return_command_id=True,
    )
    return DeviceCommand(command_id=command_id, row_id=row_id)


def enqueue_set_face(device_id: str, state: str, job_id: str | None = None, **extra: Any) -> DeviceCommand:
    command_id, row_id = enqueue_device_command(
        device_id,
        "set_face",
        {"state": state, "job_id": job_id, **extra},
        job_id=job_id,
        return_command_id=True,
    )
    return DeviceCommand(command_id=command_id, row_id=row_id)
