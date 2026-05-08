from __future__ import annotations

from typing import Any

from app.db.database import get_connection


FINAL_STATUSES = {"completed", "failed"}


def create_job(
    job_id: str,
    device_id: str,
    input_audio_path: str | None = None,
    input_audio_url: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audio_chat_job (
                job_id, device_id, status, input_audio_path, input_audio_url
            )
            VALUES (?, ?, 'accepted', ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                device_id = excluded.device_id,
                input_audio_path = COALESCE(excluded.input_audio_path, audio_chat_job.input_audio_path),
                input_audio_url = COALESCE(excluded.input_audio_url, audio_chat_job.input_audio_url),
                updated_at = CURRENT_TIMESTAMP
            """,
            (job_id, device_id, input_audio_path, input_audio_url),
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM audio_chat_job
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def update_status(job_id: str, status: str, **fields: Any) -> None:
    updates = _allowed_updates(fields)
    updates["status"] = status
    if status in FINAL_STATUSES:
        updates["completed_at"] = _sql_current_timestamp()
    _update_job(job_id, updates)


def mark_stt_done(job_id: str, user_text: str, provider: str, model: str, latency_ms: int) -> None:
    _update_job(
        job_id,
        {
            "status": "stt_done",
            "user_text": user_text,
            "stt_provider": provider,
            "stt_model": model,
            "stt_latency_ms": latency_ms,
        },
    )


def mark_llm_done(job_id: str, assistant_text: str, provider: str, model: str, latency_ms: int) -> None:
    _update_job(
        job_id,
        {
            "status": "llm_done",
            "assistant_text": assistant_text,
            "llm_provider": provider,
            "llm_model": model,
            "llm_latency_ms": latency_ms,
        },
    )


def mark_tts_done(
    job_id: str,
    reply_audio_path: str,
    reply_audio_url: str,
    provider: str,
    model: str,
    voice: str,
    latency_ms: int,
) -> None:
    _update_job(
        job_id,
        {
            "status": "tts_done",
            "reply_audio_path": reply_audio_path,
            "reply_audio_url": reply_audio_url,
            "tts_provider": provider,
            "tts_model": model,
            "tts_voice": voice,
            "tts_latency_ms": latency_ms,
        },
    )


def mark_command_queued(job_id: str, command_id: str, total_latency_ms: int | None = None) -> None:
    updates: dict[str, Any] = {
        "status": "command_queued",
        "command_id": command_id,
    }
    if total_latency_ms is not None:
        updates["total_latency_ms"] = total_latency_ms
    _update_job(job_id, updates)


def mark_completed(job_id: str) -> None:
    _update_job(
        job_id,
        {
            "status": "completed",
            "completed_at": _sql_current_timestamp(),
        },
    )


def mark_failed(job_id: str, error_code: str, error_message: str, total_latency_ms: int | None = None) -> None:
    updates: dict[str, Any] = {
        "status": "failed",
        "error_code": error_code,
        "error_message": error_message,
        "completed_at": _sql_current_timestamp(),
    }
    if total_latency_ms is not None:
        updates["total_latency_ms"] = total_latency_ms
    _update_job(job_id, updates)


def to_api(job: dict[str, Any] | None, job_id: str) -> dict[str, Any]:
    if job is None:
        return {"job_id": job_id, "status": "not_found"}
    return {
        "job_id": job["job_id"],
        "device_id": job["device_id"],
        "status": job["status"],
        "user_text": job["user_text"],
        "assistant_text": job["assistant_text"],
        "reply_audio_url": job["reply_audio_url"],
        "latency": {
            "stt_latency_ms": job["stt_latency_ms"],
            "llm_latency_ms": job["llm_latency_ms"],
            "tts_latency_ms": job["tts_latency_ms"],
            "total_latency_ms": job["total_latency_ms"],
        },
        "models": {
            "stt": _model_name(job, "stt"),
            "llm": _model_name(job, "llm"),
            "tts": _model_name(job, "tts"),
        },
        "command_id": job["command_id"],
        "error_code": job["error_code"],
        "error_message": job["error_message"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "completed_at": job["completed_at"],
    }


def _model_name(job: dict[str, Any], prefix: str) -> str | None:
    model = job.get(f"{prefix}_model")
    if prefix == "tts" and job.get("tts_voice"):
        return f"{model}:{job['tts_voice'].rsplit(':', 1)[-1]}" if model else job["tts_voice"]
    return model


def _allowed_updates(fields: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "input_audio_path",
        "input_audio_url",
        "user_text",
        "assistant_text",
        "reply_audio_path",
        "reply_audio_url",
        "stt_provider",
        "stt_model",
        "llm_provider",
        "llm_model",
        "tts_provider",
        "tts_model",
        "tts_voice",
        "stt_latency_ms",
        "llm_latency_ms",
        "tts_latency_ms",
        "total_latency_ms",
        "command_id",
        "error_code",
        "error_message",
    }
    return {key: value for key, value in fields.items() if key in allowed}


def _update_job(job_id: str, updates: dict[str, Any]) -> None:
    if not updates:
        return
    set_parts: list[str] = []
    values: list[Any] = []
    for key, value in updates.items():
        if value == _sql_current_timestamp():
            set_parts.append(f"{key} = CURRENT_TIMESTAMP")
        else:
            set_parts.append(f"{key} = ?")
            values.append(value)
    values.append(job_id)
    with get_connection() as conn:
        conn.execute(
            f"""
            UPDATE audio_chat_job
            SET {", ".join(set_parts)}, updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
            """,
            values,
        )


def _sql_current_timestamp() -> str:
    return "__CURRENT_TIMESTAMP__"
