from __future__ import annotations

from pathlib import Path
from typing import Any

from app.providers.stt.base import STTProvider, STTResult
from app.services.stt_service import SenseVoiceHTTPSTTService


class FunASRLocalSTTProvider(STTProvider):
    provider = "funasr_local"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.model = str(cfg.get("model") or "FunAudioLLM/SenseVoiceSmall")
        self.service = SenseVoiceHTTPSTTService()

    def transcribe(self, audio_path: Path, language: str = "zh") -> STTResult:
        result = self.service.transcribe(audio_path)
        return STTResult(
            text=result.text,
            language=language,
            provider=self.provider,
            model=self.model,
            latency_ms=result.latency_ms,
            confidence=result.confidence,
        )
