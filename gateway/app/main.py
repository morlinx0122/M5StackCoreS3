from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.api.routes import router
from app.db.database import init_db
from app.realtime.ws_device_api import router as realtime_router

STATIC_ROOT = Path("app/static")
for audio_dir in ("input", "reply", "system"):
    (STATIC_ROOT / "audio" / audio_dir).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # P5: warm up LLM connection so the first user request doesn't pay the
    # TLS/handshake/cold-start cost.
    try:
        import asyncio
        from app.services.llm_router import get_llm_router

        def _prewarm():
            try:
                router = get_llm_router()
                router.chat(user_text="ping", scenario="deskbot", device_id="prewarm")
                print("[prewarm] LLM warmed up", flush=True)
            except Exception as exc:
                print(f"[prewarm] LLM warmup failed: {exc}", flush=True)

        asyncio.get_event_loop().run_in_executor(None, _prewarm)
    except Exception as exc:
        print(f"[prewarm] scheduling failed: {exc}", flush=True)
    yield


app = FastAPI(
    title="DeepNexus AI Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(realtime_router)
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
