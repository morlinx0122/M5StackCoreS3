from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.services.audio_service import (
    accept_audio_chat,
    accept_wake_audio_chat,
    get_audio_job,
    get_audio_latency_summary,
    get_latest_audio_chats,
    process_audio_chat,
    process_wake_audio_chat,
)
from app.services.device_service import (
    ack_device_command,
    get_pending_device_commands,
    register_device,
    record_device_event,
    record_device_status,
    update_heartbeat,
)
from app.services.llm_service import run_chat
from app.services.stt_router import get_stt_router
from app.utils.response import ok

router = APIRouter()


@router.get("/health")
def health(request: Request):
    return ok(
        request,
        {
            "status": "ok",
            "service": "deepnexus-ai-gateway",
            "version": "0.1.0",
        },
    )


@router.post("/audio/chat")
async def audio_chat(
    request: Request,
    background_tasks: BackgroundTasks,
    device_id: str = Form(...),
    state: str | None = Form(None),
    audio: UploadFile = File(...),
):
    content = await audio.read()
    result = await accept_audio_chat(
        device_id=device_id,
        state=state,
        filename=audio.filename,
        content_type=audio.content_type,
        content=content,
    )
    background_tasks.add_task(
        process_audio_chat,
        result["job_id"],
        device_id,
        state,
        audio.filename,
        audio.content_type,
        content,
    )
    return ok(request, result)


@router.get("/audio/chat/jobs/{job_id}")
def audio_chat_job(request: Request, job_id: str):
    return ok(request, get_audio_job(job_id))


@router.get("/audio/chat/{job_id}")
def audio_chat_job_short(request: Request, job_id: str):
    return ok(request, get_audio_job(job_id))


@router.post("/audio/wake_chat")
async def audio_wake_chat(
    request: Request,
    background_tasks: BackgroundTasks,
    device_id: str = Form(...),
    state: str | None = Form(None),
    audio: UploadFile = File(...),
):
    content = await audio.read()
    result = await accept_wake_audio_chat(
        device_id=device_id,
        state=state,
        filename=audio.filename,
        content_type=audio.content_type,
        content=content,
    )
    background_tasks.add_task(
        process_wake_audio_chat,
        device_id,
        state,
        audio.filename,
        audio.content_type,
        content,
    )
    return ok(request, result)


@router.get("/debug/audio/latest")
def debug_audio_latest(request: Request, limit: int = 10):
    return ok(request, {"items": get_latest_audio_chats(limit=limit)})


@router.get("/debug/audio/latency")
def debug_audio_latency(request: Request, limit: int = 50):
    return ok(request, get_audio_latency_summary(limit=limit))


@router.post("/audio/transcribe")
async def audio_transcribe(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form("zh"),
):
    from pathlib import Path
    from uuid import uuid4

    input_root = Path("app/static/audio/input")
    input_root.mkdir(parents=True, exist_ok=True)
    safe_name = Path(audio.filename or "wake.wav").name
    suffix = Path(safe_name).suffix or ".wav"
    stored_path = input_root / f"wake_{uuid4().hex}{suffix}"
    stored_path.write_bytes(await audio.read())
    result = await run_in_threadpool(get_stt_router().transcribe, stored_path, language)
    return ok(
        request,
        {
            "text": result.text,
            "provider": result.provider,
            "latency_ms": result.latency_ms,
            "confidence": result.confidence,
            "language": language,
        },
    )


@router.post("/ai/chat")
async def ai_chat(request: Request):
    payload = await request.json()
    user_text = str(payload.get("user_text") or payload.get("message") or "")
    scenario = str(payload.get("scenario") or "deskbot")
    result = run_chat(user_text=user_text, scenario=scenario)
    return ok(
        request,
        {
            "user_text": user_text,
            "assistant_text": result["assistant_text"],
            "scenario": scenario,
            "llm": result["llm"],
        },
    )


@router.post("/device/register")
async def device_register(request: Request):
    payload = await request.json()
    device = register_device(payload)
    return ok(request, device)


@router.post("/device/heartbeat")
async def device_heartbeat(request: Request):
    payload = await request.json()
    result = update_heartbeat(payload)
    return ok(request, result)


@router.post("/device/status")
async def device_status(request: Request):
    payload = await request.json()
    result = record_device_status(payload)
    return ok(request, result)


@router.get("/device/{device_id}/commands")
def device_commands(request: Request, device_id: str):
    return ok(request, {"device_id": device_id, "commands": get_pending_device_commands(device_id)})


@router.post("/device/{device_id}/commands/{cmd_id}/ack")
async def device_command_ack(request: Request, device_id: str, cmd_id: str):
    payload = await request.json()
    return ok(request, ack_device_command(device_id, cmd_id, payload))


@router.post("/device/{device_id}/event")
async def device_event(request: Request, device_id: str):
    payload = await request.json()
    result = record_device_event(device_id, payload)
    return ok(request, result)
