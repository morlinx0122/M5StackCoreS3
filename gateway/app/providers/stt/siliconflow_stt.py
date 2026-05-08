from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from app.providers.stt.base import STTProvider, STTResult
from app.services.stt_service import clean_sensevoice_text


class SiliconFlowSTTProvider(STTProvider):
    provider = "siliconflow_stt"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        api_key = os.getenv("SILICONFLOW_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("SILICONFLOW_API_KEY is required when using siliconflow_stt.")

        self.api_key = api_key
        self.base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
        self.model = str(cfg.get("model") or os.getenv("SILICONFLOW_STT_MODEL") or "FunAudioLLM/SenseVoiceSmall")
        self.timeout_seconds = float(
            cfg.get("timeout_sec") or os.getenv("SILICONFLOW_STT_TIMEOUT_SECONDS") or 60
        )

    def transcribe(self, audio_path: Path, language: str = "zh") -> STTResult:
        started = perf_counter()
        with audio_path.open("rb") as audio_file:
            response = httpx.post(
                f"{self.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                data={"model": self.model},
                files={"file": (audio_path.name, audio_file, "audio/wav")},
                timeout=self.timeout_seconds,
                trust_env=False,
            )
        response.raise_for_status()
        payload = response.json()
        return STTResult(
            text=clean_sensevoice_text(str(payload.get("text") or "")),
            language=language,
            provider=self.provider,
            model=self.model,
            latency_ms=int((perf_counter() - started) * 1000),
            raw=payload,
        )
