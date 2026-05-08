import os
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile


app = FastAPI(title="DeepNexus SenseVoice STT Service", version="0.1.0")


class SenseVoiceEngine:
    def __init__(self) -> None:
        self.model: Any | None = None
        self.model_name = os.getenv("SENSEVOICE_MODEL", "iic/SenseVoiceSmall")
        self.device = os.getenv("SENSEVOICE_DEVICE", "cpu")
        self.hub = os.getenv("SENSEVOICE_HUB", "ms")
        self.use_itn = os.getenv("SENSEVOICE_USE_ITN", "true").lower() == "true"
        self.batch_size_s = int(os.getenv("SENSEVOICE_BATCH_SIZE_S", "60"))

    def load(self) -> None:
        if self.model is not None:
            return

        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "funasr is not installed. Install optional SenseVoice dependencies first."
            ) from exc

        self.model = AutoModel(
            model=self.model_name,
            trust_remote_code=True,
            hub=self.hub,
            device=self.device,
        )

    def transcribe(self, audio_path: Path, language: str) -> dict[str, Any]:
        self.load()
        assert self.model is not None

        started = perf_counter()
        result = self.model.generate(
            input=str(audio_path),
            cache={},
            language=language,
            use_itn=self.use_itn,
            batch_size_s=self.batch_size_s,
        )
        latency_ms = int((perf_counter() - started) * 1000)
        text = extract_text(result)

        return {
            "text": text,
            "language": language,
            "model": self.model_name,
            "provider": "sensevoice_small",
            "latency_ms": latency_ms,
            "raw": result,
        }


engine = SenseVoiceEngine()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "sensevoice-stt",
        "model": engine.model_name,
        "device": engine.device,
        "loaded": engine.model is not None,
    }


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: str = Form("zh"),
) -> dict[str, Any]:
    suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        temp_file.write(await audio.read())

    try:
        return engine.transcribe(temp_path, language=language)
    finally:
        temp_path.unlink(missing_ok=True)


def extract_text(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()

    if isinstance(result, dict):
        return text_from_dict(result)

    if isinstance(result, list):
        parts: list[str] = []
        for item in result:
            if isinstance(item, dict):
                text = text_from_dict(item)
                if text:
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()

    return str(result).strip()


def text_from_dict(payload: dict[str, Any]) -> str:
    for key in ("text", "sentence", "transcript"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    value = payload.get("result")
    if isinstance(value, dict):
        nested = text_from_dict(value)
        if nested:
            return nested

    value = payload.get("data")
    if isinstance(value, dict):
        nested = text_from_dict(value)
        if nested:
            return nested

    return ""
