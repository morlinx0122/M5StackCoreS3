from __future__ import annotations

from typing import Any

from app.db.database import get_connection


def create_session(session_id: str, device_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO realtime_voice_session (session_id, device_id, status)
            VALUES (?, ?, 'listening')
            ON CONFLICT(session_id) DO UPDATE SET
                device_id = excluded.device_id,
                status = 'listening',
                updated_at = CURRENT_TIMESTAMP
            """,
            (session_id, device_id),
        )


def mark(session_id: str, status: str | None = None, **fields: Any) -> None:
    allowed = {
        "partial_text",
        "final_text",
        "assistant_text",
        "intent",
        "fast_intent_hit",
        "user_emotion",
        "user_event",
        "stt_provider",
        "stt_streaming_model",
        "stt_final_model",
        "llm_provider",
        "llm_model",
        "tts_provider",
        "tts_model",
        "tts_voice",
        "first_response_latency_ms",
        "total_latency_ms",
        "error_code",
        "error_message",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    timestamp_fields = {
        key
        for key in fields
        if key
        in {
            "first_audio_in_at",
            "speech_end_at",
            "stt_final_at",
            "fast_intent_done_at",
            "llm_first_token_at",
            "llm_first_sentence_at",
            "tts_first_audio_at",
            "playback_start_at",
            "playback_end_at",
        }
    }
    set_parts: list[str] = []
    values: list[Any] = []
    if status is not None:
        set_parts.append("status = ?")
        values.append(status)
    for key, value in updates.items():
        set_parts.append(f"{key} = ?")
        values.append(value)
    for key in timestamp_fields:
        set_parts.append(f"{key} = CURRENT_TIMESTAMP")
    if not set_parts:
        return
    values.append(session_id)
    with get_connection() as conn:
        conn.execute(
            f"""
            UPDATE realtime_voice_session
            SET {", ".join(set_parts)}, updated_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
            """,
            values,
        )
