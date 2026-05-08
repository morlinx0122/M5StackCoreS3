from __future__ import annotations

import os
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile

from optional_services.sensevoice_server import extract_text


app = FastAPI(title="DeepNexus FunASR Realtime Service", version="0.1.0")


class FunASRRealtimeEngine:
    def __init__(self) -> None:
        self.streaming_model: Any | None = None
        self.vad_model: Any | None = None
        self.final_model: Any | None = None
        self.streaming_model_name = os.getenv("FUNASR_STREAMING_MODEL", "paraformer-zh-streaming")
        self.vad_model_name = os.getenv("FUNASR_VAD_MODEL", "fsmn-vad")
        self.final_model_name = os.getenv("FUNASR_FINAL_MODEL", "iic/SenseVoiceSmall")
        self.device = os.getenv("FUNASR_DEVICE", os.getenv("SENSEVOICE_DEVICE", "cpu"))
        self.hub = os.getenv("FUNASR_HUB", os.getenv("SENSEVOICE_HUB", "ms"))
        self.use_itn = os.getenv("FUNASR_USE_ITN", "true").lower() == "true"
        self.batch_size_s = int(os.getenv("FUNASR_BATCH_SIZE_S", "60"))

    def load_streaming(self) -> None:
        if self.streaming_model is not None:
            return
        from funasr import AutoModel

        self.streaming_model = AutoModel(
            model=self.streaming_model_name,
            hub=self.hub,
            device=self.device,
        )

    def load_vad(self) -> None:
        if self.vad_model is not None:
            return
        from funasr import AutoModel

        self.vad_model = AutoModel(
            model=self.vad_model_name,
            hub=self.hub,
            device=self.device,
        )

    def load_final(self) -> None:
        if self.final_model is not None:
            return
        from funasr import AutoModel

        self.final_model = AutoModel(
            model=self.final_model_name,
            trust_remote_code=True,
            hub=self.hub,
            device=self.device,
        )

    def partial(self, audio_path: Path, is_final: bool) -> dict[str, Any]:
        self.load_streaming()
        assert self.streaming_model is not None
        started = perf_counter()
        # Each request is an independent snapshot of accumulated PCM (no
        # cross-request cache), so we always finalize the streaming chunk to
        # avoid empty-feature errors on short clips.
        result = self.streaming_model.generate(
            input=str(audio_path),
            cache={},
            is_final=True,
            chunk_size=[0, 10, 5],
            encoder_chunk_look_back=4,
            decoder_chunk_look_back=1,
        )
        return {
            "text": extract_text(result),
            "provider": "funasr_local",
            "model": self.streaming_model_name,
            "latency_ms": int((perf_counter() - started) * 1000),
            "raw": result,
        }

    def vad(self, audio_path: Path) -> dict[str, Any]:
        self.load_vad()
        assert self.vad_model is not None
        started = perf_counter()
        result = self.vad_model.generate(
            input=str(audio_path),
            cache={},
            is_final=True,
            chunk_size=200,
        )
        speech_segments = _extract_speech_segments(result)
        return {
            "speech_segments": speech_segments,
            "speech_detected": bool(speech_segments),
            "provider": "funasr_local",
            "model": self.vad_model_name,
            "latency_ms": int((perf_counter() - started) * 1000),
            "raw": result,
        }

    def final(self, audio_path: Path, language: str) -> dict[str, Any]:
        self.load_final()
        assert self.final_model is not None
        started = perf_counter()
        result = self.final_model.generate(
            input=str(audio_path),
            cache={},
            language=language,
            use_itn=self.use_itn,
            batch_size_s=self.batch_size_s,
        )
        return {
            "text": extract_text(result),
            "language": language,
            "provider": "funasr_local",
            "model": self.final_model_name,
            "latency_ms": int((perf_counter() - started) * 1000),
            "raw": result,
        }


engine = FunASRRealtimeEngine()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "funasr-realtime",
        "streaming_model": engine.streaming_model_name,
        "vad_model": engine.vad_model_name,
        "final_model": engine.final_model_name,
        "device": engine.device,
        "loaded": {
            "streaming": engine.streaming_model is not None,
            "vad": engine.vad_model is not None,
            "final": engine.final_model is not None,
        },
    }


@app.post("/partial")
async def partial(audio: UploadFile = File(...), is_final: bool = Form(False)) -> dict[str, Any]:
    return await _with_temp_audio(audio, lambda path: engine.partial(path, is_final=is_final))


@app.post("/vad")
async def vad(audio: UploadFile = File(...)) -> dict[str, Any]:
    return await _with_temp_audio(audio, engine.vad)


@app.post("/final")
async def final(audio: UploadFile = File(...), language: str = Form("zh")) -> dict[str, Any]:
    return await _with_temp_audio(audio, lambda path: engine.final(path, language=language))


async def _with_temp_audio(audio: UploadFile, handler):
    suffix = Path(audio.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = Path(temp_file.name)
        temp_file.write(await audio.read())
    try:
        return handler(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def _extract_speech_segments(result: Any) -> list[list[int]]:
    if isinstance(result, dict):
        value = result.get("value") or result.get("segments") or result.get("speech_segments")
        if isinstance(value, list):
            return value
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                value = item.get("value") or item.get("segments") or item.get("speech_segments")
                if isinstance(value, list):
                    return value
    return []
