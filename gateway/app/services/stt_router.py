from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.model_config import model_section
from app.providers.stt.base import STTProvider, STTResult
from app.providers.stt.funasr_local import FunASRLocalSTTProvider
from app.providers.stt.siliconflow_stt import SiliconFlowSTTProvider
from app.services.stt_service import get_stt_service


class LegacySTTProvider(STTProvider):
    def __init__(self, provider_name: str) -> None:
        self.provider = provider_name
        self.service = get_stt_service()
        self.model = getattr(self.service, "model", provider_name)

    def transcribe(self, audio_path: Path, language: str = "zh") -> STTResult:
        result = self.service.transcribe(audio_path)
        return STTResult(
            text=result.text,
            language=language,
            provider=result.provider,
            model=str(getattr(self.service, "model", self.model)),
            latency_ms=result.latency_ms,
            confidence=result.confidence,
        )


class STTRouter:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or model_section("stt")
        primary_config = self.config.get("primary") if isinstance(self.config.get("primary"), dict) else {}
        self.primary = build_stt_provider(primary_config)
        self.fallbacks = [
            build_stt_provider(fallback)
            for fallback in self.config.get("fallback", [])
            if isinstance(fallback, dict) and fallback.get("enabled")
        ]

    def transcribe(self, audio_path: Path, language: str = "zh") -> STTResult:
        try:
            return self.primary.transcribe(audio_path, language)
        except Exception as primary_error:
            for provider in self.fallbacks:
                try:
                    return provider.transcribe(audio_path, language)
                except Exception as fallback_error:
                    print(f"STT fallback failed provider={provider.provider} error={fallback_error}", flush=True)
            raise primary_error


def build_stt_provider(config: dict[str, Any]) -> STTProvider:
    provider = str(config.get("provider") or "mock").strip().lower()
    if provider == "siliconflow_stt":
        return SiliconFlowSTTProvider(config)
    if provider == "funasr_local":
        return FunASRLocalSTTProvider(config)
    return LegacySTTProvider(provider)


def get_stt_router() -> STTRouter:
    return STTRouter()
