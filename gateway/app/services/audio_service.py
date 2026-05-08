import re
from pathlib import Path
from typing import Any
from time import perf_counter
from uuid import uuid4

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.db.database import get_connection
from app.services import job_service
from app.services.command_service import enqueue_play_audio, enqueue_set_face
from app.services.device_service import enqueue_device_command
from app.services.fast_intent_router import route_fast_intent
from app.services.llm_router import get_llm_router
from app.services.stt_router import get_stt_router
from app.services.tts_router import get_tts_router

AUDIO_ROOT = Path("app/static/audio")
INPUT_ROOT = AUDIO_ROOT / "input"
WAKE_WORDS = ("桌面机器人", "小助手", "你好机器人", "嘿机器人")


async def save_audio_chat(device_id: str, state: str | None, audio: UploadFile) -> dict[str, Any]:
    content = await audio.read()
    job_id = create_audio_job(
        device_id=device_id,
        state=state,
        filename=audio.filename,
        content_type=audio.content_type,
        content=content,
    )
    return await run_in_threadpool(
        process_audio_chat,
        job_id,
        device_id,
        state,
        audio.filename,
        audio.content_type,
        content,
    )


def process_audio_chat(
    job_id: str,
    device_id: str,
    state: str | None,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> dict[str, Any]:
    update_audio_job(job_id, status="stt_running")
    job_service.update_status(job_id, "stt_running")
    try:
        result = _process_audio_chat_pipeline(job_id, device_id, state, filename, content_type, content)
    except Exception as exc:
        update_audio_job(
            job_id,
            status="failed",
            error_code=exc.__class__.__name__,
            error_message=str(exc),
        )
        job_service.mark_failed(job_id, "AUDIO_CHAT_PIPELINE_FAILED", str(exc))
        try:
            fallback_audio = get_tts_router().get_cached_error_audio("sorry_retry")
            enqueue_play_audio(
                device_id=device_id,
                job_id=job_id,
                audio_url=fallback_audio.audio_url,
                text="我刚刚没有听清楚，可以再说一遍吗？",
                emotion="sorry",
                face_state="ERROR",
            )
        except Exception:
            enqueue_set_face(device_id, "IDLE", job_id=job_id, reason="job_failed")
        print(f"Audio chat job failed job_id={job_id} error={exc}", flush=True)
        raise

    update_audio_job(
        job_id,
        status="command_queued",
        stt_text=str(result.get("user_text") or ""),
        llm_text=str(result.get("assistant_text") or ""),
        tts_audio_url=str(result.get("audio_url") or ""),
    )
    return result


def _process_audio_chat_pipeline(
    job_id: str,
    device_id: str,
    state: str | None,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> dict[str, Any]:
    INPUT_ROOT.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename or "input.wav").name
    suffix = Path(safe_name).suffix or ".wav"
    asset_id = f"aud_{uuid4().hex}"
    stored_name = f"{asset_id}{suffix}"
    stored_path = INPUT_ROOT / stored_name

    stored_path.write_bytes(content)
    update_audio_job(job_id, audio_path=str(stored_path))
    relative_url = f"/static/audio/input/{stored_name}"
    job_service.update_status(
        job_id,
        "stt_running",
        input_audio_path=str(stored_path),
        input_audio_url=relative_url,
    )
    started = perf_counter()
    stt_result = get_stt_router().transcribe(stored_path, language="zh")
    print(
        f"Audio chat STT done provider={stt_result.provider} "
        f"latency_ms={stt_result.latency_ms} text={stt_result.text}",
        flush=True,
    )
    update_audio_job(job_id, status="llm_running", stt_text=stt_result.text)
    job_service.mark_stt_done(
        job_id=job_id,
        user_text=stt_result.text,
        provider=stt_result.provider,
        model=stt_result.model,
        latency_ms=stt_result.latency_ms,
    )

    fast_intent = route_fast_intent(stt_result.text)
    if fast_intent is not None:
        result = _finish_fast_intent_audio_chat(
            job_id=job_id,
            device_id=device_id,
            state=state,
            asset_id=asset_id,
            safe_name=safe_name,
            content_type=content_type,
            content_size=len(content),
            stored_path=stored_path,
            relative_url=relative_url,
            stt_result=stt_result,
            fast_intent=fast_intent,
            started=started,
        )
        update_audio_job(job_id, status="command_queued", llm_text=result["assistant_text"])
        return result

    job_service.update_status(job_id, "llm_running")
    llm_result = get_llm_router().chat(
        user_text=stt_result.text,
        scenario="deskbot_voice_short_reply",
        device_id=device_id,
    )
    print(
        f"Audio chat LLM done provider={llm_result.provider} "
        f"model={llm_result.model} latency_ms={llm_result.latency_ms}",
        flush=True,
    )
    update_audio_job(job_id, status="tts_running", llm_text=llm_result.text)
    job_service.mark_llm_done(
        job_id=job_id,
        assistant_text=llm_result.text,
        provider=llm_result.provider,
        model=llm_result.model,
        latency_ms=llm_result.latency_ms,
    )
    job_service.update_status(job_id, "tts_running")
    tts_text = prepare_tts_text(llm_result.text)
    tts_result = get_tts_router().synthesize(tts_text)
    print(
        f"Audio chat TTS done provider={tts_result.provider} "
        f"latency_ms={tts_result.latency_ms} size={tts_result.size_bytes} "
        f"total_ms={int((perf_counter() - started) * 1000)}",
        flush=True,
    )
    total_latency_ms = int((perf_counter() - started) * 1000)
    job_service.mark_tts_done(
        job_id=job_id,
        reply_audio_path=str(tts_result.file_path),
        reply_audio_url=tts_result.audio_url,
        provider=tts_result.provider,
        model=tts_result.model,
        voice=tts_result.voice,
        latency_ms=tts_result.latency_ms,
    )

    reply_asset_id = tts_result.audio_url.rsplit("/", 1)[-1].removesuffix(".wav")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audio_asset (
                asset_id, device_id, kind, original_filename, content_type,
                file_path, file_url, size_bytes, stt_provider, stt_text, stt_latency_ms
            )
            VALUES (?, ?, 'user_input', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                device_id,
                safe_name,
                content_type,
                str(stored_path),
                relative_url,
                len(content),
                stt_result.provider,
                stt_result.text,
                stt_result.latency_ms,
            ),
        )
        conn.execute(
            """
            INSERT INTO audio_asset (
                asset_id, device_id, kind, original_filename, content_type,
                file_path, file_url, size_bytes
            )
            VALUES (?, ?, 'assistant_reply', ?, 'audio/wav', ?, ?, ?)
            """,
            (
                reply_asset_id,
                device_id,
                "reply.wav",
                str(tts_result.file_path),
                tts_result.audio_url,
                tts_result.size_bytes,
            ),
        )
        conn.execute(
            """
            INSERT INTO audio_chat_log (
                device_id, state, user_asset_id, reply_asset_id, user_audio_url, reply_audio_url,
                user_text, assistant_text, tts_text, stt_provider, stt_latency_ms, stt_confidence,
                llm_provider, llm_model, llm_latency_ms, llm_finish_reason,
                tts_provider, tts_latency_ms, tts_sample_rate, tts_size_bytes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                state,
                asset_id,
                reply_asset_id,
                relative_url,
                tts_result.audio_url,
                stt_result.text,
                llm_result.text,
                tts_text,
                stt_result.provider,
                stt_result.latency_ms,
                stt_result.confidence,
                llm_result.provider,
                llm_result.model,
                llm_result.latency_ms,
                llm_result.finish_reason,
                tts_result.provider,
                tts_result.latency_ms,
                tts_result.sample_rate,
                tts_result.size_bytes,
            ),
        )

    command = enqueue_play_audio(
        device_id=device_id,
        job_id=job_id,
        audio_url=tts_result.audio_url,
        text=tts_text,
        emotion=llm_result.emotion or "happy",
        face_state=llm_result.face_state or "SPEAKING",
    )
    job_service.mark_command_queued(job_id, command.command_id, total_latency_ms=total_latency_ms)

    return {
        "user_text": stt_result.text,
        "assistant_text": llm_result.text,
        "tts_text": tts_text,
        "intent": "chat",
        "agent": "chat_agent",
        "emotion": "happy",
        "face_state": llm_result.face_state or "SPEAKING",
        "stt": {
            "provider": stt_result.provider,
            "model": stt_result.model,
            "latency_ms": stt_result.latency_ms,
            "confidence": stt_result.confidence,
        },
        "llm": {
            "provider": llm_result.provider,
            "model": llm_result.model,
            "latency_ms": llm_result.latency_ms,
            "finish_reason": llm_result.finish_reason,
        },
        "tts": {
            "provider": tts_result.provider,
            "model": tts_result.model,
            "voice": tts_result.voice,
            "latency_ms": tts_result.latency_ms,
            "sample_rate": tts_result.sample_rate,
            "size_bytes": tts_result.size_bytes,
        },
        "audio_url": tts_result.audio_url,
        "audio_asset": {
            "asset_id": asset_id,
            "url": relative_url,
            "size_bytes": len(content),
            "content_type": content_type,
        },
        "device_actions": [
            {
                "type": "play_audio",
                "url": tts_result.audio_url,
            }
        ],
        "debug": {
            "device_id": device_id,
            "state": state,
            "filename": safe_name,
        },
    }


def _finish_fast_intent_audio_chat(
    job_id: str,
    device_id: str,
    state: str | None,
    asset_id: str,
    safe_name: str,
    content_type: str | None,
    content_size: int,
    stored_path: Path,
    relative_url: str,
    stt_result,
    fast_intent,
    started: float,
) -> dict[str, Any]:
    job_service.mark_llm_done(
        job_id=job_id,
        assistant_text=fast_intent.assistant_text,
        provider="fast_intent",
        model=fast_intent.intent,
        latency_ms=0,
    )
    job_service.update_status(job_id, "tts_running")
    tts_text = prepare_tts_text(fast_intent.assistant_text)
    tts_router = get_tts_router()
    cached_audio = (
        tts_router.get_cached_audio_if_exists(fast_intent.cached_audio_key)
        if fast_intent.cached_audio_key
        else None
    )
    tts_result = cached_audio or tts_router.synthesize(tts_text)
    total_latency_ms = int((perf_counter() - started) * 1000)
    job_service.mark_tts_done(
        job_id=job_id,
        reply_audio_path=str(tts_result.file_path),
        reply_audio_url=tts_result.audio_url,
        provider=tts_result.provider,
        model=tts_result.model,
        voice=tts_result.voice,
        latency_ms=tts_result.latency_ms,
    )

    reply_asset_id = tts_result.audio_url.rsplit("/", 1)[-1].removesuffix(".wav")
    _record_audio_chat(
        device_id=device_id,
        state=state,
        asset_id=asset_id,
        reply_asset_id=reply_asset_id,
        safe_name=safe_name,
        content_type=content_type,
        content_size=content_size,
        stored_path=stored_path,
        relative_url=relative_url,
        reply_audio_url=tts_result.audio_url,
        reply_audio_path=tts_result.file_path,
        user_text=stt_result.text,
        assistant_text=fast_intent.assistant_text,
        tts_text=tts_text,
        stt_result=stt_result,
        llm_provider="fast_intent",
        llm_model=fast_intent.intent,
        llm_latency_ms=0,
        llm_finish_reason="fast_intent",
        tts_result=tts_result,
    )

    command = enqueue_play_audio(
        device_id=device_id,
        job_id=job_id,
        audio_url=tts_result.audio_url,
        text=tts_text,
        emotion=fast_intent.emotion,
        face_state=fast_intent.face_state,
    )
    job_service.mark_command_queued(job_id, command.command_id, total_latency_ms=total_latency_ms)
    print(
        f"Audio chat fast intent done intent={fast_intent.intent} "
        f"tts_provider={tts_result.provider} total_ms={total_latency_ms}",
        flush=True,
    )
    return {
        "user_text": stt_result.text,
        "assistant_text": fast_intent.assistant_text,
        "tts_text": tts_text,
        "intent": fast_intent.intent,
        "agent": "fast_intent_router",
        "emotion": fast_intent.emotion,
        "face_state": fast_intent.face_state,
        "stt": {
            "provider": stt_result.provider,
            "model": stt_result.model,
            "latency_ms": stt_result.latency_ms,
            "confidence": stt_result.confidence,
        },
        "llm": {
            "provider": "fast_intent",
            "model": fast_intent.intent,
            "latency_ms": 0,
            "finish_reason": "fast_intent",
        },
        "tts": {
            "provider": tts_result.provider,
            "model": tts_result.model,
            "voice": tts_result.voice,
            "latency_ms": tts_result.latency_ms,
            "sample_rate": tts_result.sample_rate,
            "size_bytes": tts_result.size_bytes,
        },
        "audio_url": tts_result.audio_url,
    }


def _record_audio_chat(
    device_id: str,
    state: str | None,
    asset_id: str,
    reply_asset_id: str,
    safe_name: str,
    content_type: str | None,
    content_size: int,
    stored_path: Path,
    relative_url: str,
    reply_audio_url: str,
    reply_audio_path: Path,
    user_text: str,
    assistant_text: str,
    tts_text: str,
    stt_result,
    llm_provider: str,
    llm_model: str,
    llm_latency_ms: int,
    llm_finish_reason: str,
    tts_result,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audio_asset (
                asset_id, device_id, kind, original_filename, content_type,
                file_path, file_url, size_bytes, stt_provider, stt_text, stt_latency_ms
            )
            VALUES (?, ?, 'user_input', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                device_id,
                safe_name,
                content_type,
                str(stored_path),
                relative_url,
                content_size,
                stt_result.provider,
                user_text,
                stt_result.latency_ms,
            ),
        )
        conn.execute(
            """
            INSERT INTO audio_asset (
                asset_id, device_id, kind, original_filename, content_type,
                file_path, file_url, size_bytes
            )
            VALUES (?, ?, 'assistant_reply', ?, 'audio/wav', ?, ?, ?)
            """,
            (
                reply_asset_id,
                device_id,
                "reply.wav",
                str(reply_audio_path),
                reply_audio_url,
                tts_result.size_bytes,
            ),
        )
        conn.execute(
            """
            INSERT INTO audio_chat_log (
                device_id, state, user_asset_id, reply_asset_id, user_audio_url, reply_audio_url,
                user_text, assistant_text, tts_text, stt_provider, stt_latency_ms, stt_confidence,
                llm_provider, llm_model, llm_latency_ms, llm_finish_reason,
                tts_provider, tts_latency_ms, tts_sample_rate, tts_size_bytes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                state,
                asset_id,
                reply_asset_id,
                relative_url,
                reply_audio_url,
                user_text,
                assistant_text,
                tts_text,
                stt_result.provider,
                stt_result.latency_ms,
                stt_result.confidence,
                llm_provider,
                llm_model,
                llm_latency_ms,
                llm_finish_reason,
                tts_result.provider,
                tts_result.latency_ms,
                tts_result.sample_rate,
                tts_result.size_bytes,
            ),
        )


def process_wake_audio_chat(
    device_id: str,
    state: str | None,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> dict[str, Any]:
    INPUT_ROOT.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename or "wake.wav").name
    suffix = Path(safe_name).suffix or ".wav"
    asset_id = f"aud_{uuid4().hex}"
    stored_name = f"{asset_id}{suffix}"
    stored_path = INPUT_ROOT / stored_name
    stored_path.write_bytes(content)

    started = perf_counter()
    stt_result = get_stt_router().transcribe(stored_path, language="zh")
    print(
        f"Wake chat STT done provider={stt_result.provider} "
        f"latency_ms={stt_result.latency_ms} text={stt_result.text}",
        flush=True,
    )

    if not contains_wake_word(stt_result.text):
        print("Wake chat ignored: wake word not matched", flush=True)
        enqueue_device_command(device_id, "set_face", {"state": "IDLE", "reason": "wake_word_not_matched"})
        return {
            "status": "ignored",
            "reason": "wake_word_not_matched",
            "user_text": stt_result.text,
            "stt": {
                "provider": stt_result.provider,
                "latency_ms": stt_result.latency_ms,
                "confidence": stt_result.confidence,
            },
        }

    user_text = strip_wake_word(stt_result.text)
    if not user_text:
        user_text = "我在，请用一句很短的话提示用户可以直接说问题。"

    llm_result = get_llm_router().chat(user_text=user_text, scenario="deskbot", device_id=device_id)
    print(
        f"Wake chat LLM done provider={llm_result.provider} "
        f"model={llm_result.model} latency_ms={llm_result.latency_ms}",
        flush=True,
    )
    tts_text = prepare_tts_text(llm_result.text)
    tts_result = get_tts_router().synthesize(tts_text)
    print(
        f"Wake chat TTS done provider={tts_result.provider} "
        f"latency_ms={tts_result.latency_ms} size={tts_result.size_bytes} "
        f"total_ms={int((perf_counter() - started) * 1000)}",
        flush=True,
    )

    relative_url = f"/static/audio/input/{stored_name}"
    reply_asset_id = tts_result.audio_url.rsplit("/", 1)[-1].removesuffix(".wav")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audio_asset (
                asset_id, device_id, kind, original_filename, content_type,
                file_path, file_url, size_bytes, stt_provider, stt_text, stt_latency_ms
            )
            VALUES (?, ?, 'user_input', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                device_id,
                safe_name,
                content_type,
                str(stored_path),
                relative_url,
                len(content),
                stt_result.provider,
                stt_result.text,
                stt_result.latency_ms,
            ),
        )
        conn.execute(
            """
            INSERT INTO audio_asset (
                asset_id, device_id, kind, original_filename, content_type,
                file_path, file_url, size_bytes
            )
            VALUES (?, ?, 'assistant_reply', ?, 'audio/wav', ?, ?, ?)
            """,
            (
                reply_asset_id,
                device_id,
                "reply.wav",
                str(tts_result.file_path),
                tts_result.audio_url,
                tts_result.size_bytes,
            ),
        )
        conn.execute(
            """
            INSERT INTO audio_chat_log (
                device_id, state, user_asset_id, reply_asset_id, user_audio_url, reply_audio_url,
                user_text, assistant_text, tts_text, stt_provider, stt_latency_ms, stt_confidence,
                llm_provider, llm_model, llm_latency_ms, llm_finish_reason,
                tts_provider, tts_latency_ms, tts_sample_rate, tts_size_bytes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                state,
                asset_id,
                reply_asset_id,
                relative_url,
                tts_result.audio_url,
                user_text,
                llm_result.text,
                tts_text,
                stt_result.provider,
                stt_result.latency_ms,
                stt_result.confidence,
                llm_result.provider,
                llm_result.model,
                llm_result.latency_ms,
                llm_result.finish_reason,
                tts_result.provider,
                tts_result.latency_ms,
                tts_result.sample_rate,
                tts_result.size_bytes,
            ),
        )

    enqueue_device_command(
        device_id,
        "play_audio",
        {
            "url": tts_result.audio_url,
            "text": tts_text,
            "reply_asset_id": reply_asset_id,
        },
    )

    return {
        "status": "answered",
        "wake_text": stt_result.text,
        "user_text": user_text,
        "assistant_text": llm_result.text,
        "tts_text": tts_text,
        "audio_url": tts_result.audio_url,
    }


async def accept_audio_chat(
    device_id: str,
    state: str | None,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> dict[str, Any]:
    job_id = await run_in_threadpool(
        create_audio_job,
        device_id,
        state,
        filename,
        content_type,
        content,
    )
    return {
        "status": "accepted",
        "job_id": job_id,
        "device_id": device_id,
        "state": state,
        "audio_size_bytes": len(content),
        "filename": Path(filename or "input.wav").name,
    }


def create_audio_job(
    device_id: str,
    state: str | None,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> str:
    job_id = f"job_{uuid4().hex}"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO device_audio_job (
                job_id, device_id, status, sample_rate, channels, sample_format,
                duration_ms
            )
            VALUES (?, ?, 'accepted', 16000, 1, 's16le', NULL)
            """,
            (job_id, device_id),
        )
    job_service.create_job(job_id=job_id, device_id=device_id)
    return job_id


def update_audio_job(job_id: str, **fields: Any) -> None:
    allowed = {
        "status",
        "audio_path",
        "duration_ms",
        "stt_text",
        "llm_text",
        "tts_audio_url",
        "error_code",
        "error_message",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return

    set_clause = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values())
    values.append(job_id)
    with get_connection() as conn:
        conn.execute(
            f"""
            UPDATE device_audio_job
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
            """,
            values,
        )


def get_audio_job(job_id: str) -> dict[str, Any]:
    job = job_service.get_job(job_id)
    if job is not None:
        return job_service.to_api(job, job_id)

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT job_id, device_id, status, stt_text, llm_text, tts_audio_url,
                   error_code, error_message, created_at, updated_at
            FROM device_audio_job
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        return {"job_id": job_id, "status": "not_found"}

    return {
        "job_id": row["job_id"],
        "device_id": row["device_id"],
        "status": row["status"],
        "stt_text": row["stt_text"],
        "llm_text": row["llm_text"],
        "tts_audio_url": row["tts_audio_url"],
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def accept_wake_audio_chat(
    device_id: str,
    state: str | None,
    filename: str | None,
    content_type: str | None,
    content: bytes,
) -> dict[str, Any]:
    job_id = f"wake_{uuid4().hex}"
    await run_in_threadpool(
        enqueue_device_command,
        device_id,
        "set_face",
        {
            "state": "THINKING",
            "job_id": job_id,
        },
    )
    return {
        "status": "accepted",
        "job_id": job_id,
        "device_id": device_id,
        "state": state,
        "audio_size_bytes": len(content),
        "filename": Path(filename or "wake.wav").name,
    }


def get_latest_audio_chats(limit: int = 10) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 50))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id, device_id, state, user_asset_id, reply_asset_id,
                user_audio_url, reply_audio_url, user_text, assistant_text, tts_text,
                stt_provider, stt_latency_ms, stt_confidence,
                llm_provider, llm_model, llm_latency_ms, llm_finish_reason,
                tts_provider, tts_latency_ms, tts_sample_rate, tts_size_bytes,
                created_at
            FROM audio_chat_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "device_id": row["device_id"],
            "state": row["state"],
            "user_text": row["user_text"],
            "assistant_text": row["assistant_text"],
            "tts_text": row["tts_text"],
            "audio": {
                "user_asset_id": row["user_asset_id"],
                "reply_asset_id": row["reply_asset_id"],
                "user_audio_url": row["user_audio_url"],
                "reply_audio_url": row["reply_audio_url"],
            },
            "stt": {
                "provider": row["stt_provider"],
                "latency_ms": row["stt_latency_ms"],
                "confidence": row["stt_confidence"],
            },
            "llm": {
                "provider": row["llm_provider"],
                "model": row["llm_model"],
                "latency_ms": row["llm_latency_ms"],
                "finish_reason": row["llm_finish_reason"],
            },
            "tts": {
                "provider": row["tts_provider"],
                "latency_ms": row["tts_latency_ms"],
                "sample_rate": row["tts_sample_rate"],
                "size_bytes": row["tts_size_bytes"],
            },
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_audio_latency_summary(limit: int = 50) -> dict[str, Any]:
    safe_limit = max(5, min(limit, 200))
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT stt_latency_ms, llm_latency_ms, tts_latency_ms
            FROM audio_chat_log
            WHERE stt_latency_ms IS NOT NULL
              AND llm_latency_ms IS NOT NULL
              AND tts_latency_ms IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    samples = [
        {
            "stt": int(row["stt_latency_ms"]),
            "llm": int(row["llm_latency_ms"]),
            "tts": int(row["tts_latency_ms"]),
            "total": int(row["stt_latency_ms"]) + int(row["llm_latency_ms"]) + int(row["tts_latency_ms"]),
        }
        for row in rows
    ]
    return {
        "sample_count": len(samples),
        "window_limit": safe_limit,
        "stt": _latency_stats([item["stt"] for item in samples]),
        "llm": _latency_stats([item["llm"] for item in samples]),
        "tts": _latency_stats([item["tts"] for item in samples]),
        "total": _latency_stats([item["total"] for item in samples]),
    }


def _latency_stats(values: list[int]) -> dict[str, int | None]:
    if not values:
        return {"avg_ms": None, "p50_ms": None, "p90_ms": None}
    ordered = sorted(values)
    return {
        "avg_ms": int(sum(ordered) / len(ordered)),
        "p50_ms": _percentile(ordered, 0.50),
        "p90_ms": _percentile(ordered, 0.90),
    }


def _percentile(ordered_values: list[int], percentile: float) -> int:
    if len(ordered_values) == 1:
        return ordered_values[0]
    index = round((len(ordered_values) - 1) * percentile)
    return ordered_values[index]


def prepare_tts_text(text: str) -> str:
    cleaned = re.sub(r"<\|[^|]+?\|>", "", text)
    cleaned = re.sub(r"desk\s*bot|deskbot", "桌面机器人", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[，,]{2,}", "，", cleaned)
    cleaned = re.sub(r"[。\.]{2,}", "。", cleaned)
    cleaned = re.sub(r"[！!]{2,}", "！", cleaned)
    cleaned = re.sub(r"[？?]{2,}", "？", cleaned)
    cleaned = re.sub(r"，([。！？])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def normalize_wake_text(text: str) -> str:
    return re.sub(r"[\s,，.。!！?？:：;；、]", "", text or "")


def contains_wake_word(text: str) -> bool:
    normalized = normalize_wake_text(text)
    return any(word in normalized for word in WAKE_WORDS)


def strip_wake_word(text: str) -> str:
    cleaned = text or ""
    for word in WAKE_WORDS:
        cleaned = cleaned.replace(word, "")
    cleaned = re.sub(r"^[\s,，.。!！?？:：;；、]+", "", cleaned)
    return cleaned.strip()
