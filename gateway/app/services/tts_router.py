from __future__ import annotations

from typing import Any

from app.core.model_config import model_section
from app.providers.tts.base import TTSProvider, TTSResult
from app.providers.tts.cached_audio_tts import CachedAudioTTSProvider
from app.providers.tts.siliconflow_tts import SiliconFlowTTSProvider
from app.services.tts_service import get_tts_service


class LegacyTTSProvider(TTSProvider):
    def __init__(self, config: dict[str, Any]) -> None:
        self.provider = str(config.get("provider") or "mock").strip().lower()
        self.service = get_tts_service()
        self.model = str(config.get("model") or getattr(self.service, "model", self.provider))
        self.voice = str(config.get("voice") or getattr(self.service, "voice", self.provider))

    def synthesize(self, text: str, voice: str | None = None, audio_format: str = "wav") -> TTSResult:
        result = self.service.synthesize(text)
        return TTSResult(
            audio_url=result.audio_url,
            file_path=result.file_path,
            provider=result.provider,
            model=str(getattr(self.service, "model", self.model)),
            voice=str(voice or getattr(self.service, "voice", self.voice)),
            latency_ms=result.latency_ms,
            size_bytes=result.size_bytes,
            sample_rate=result.sample_rate,
        )


class TTSRouter:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or model_section("tts")
        primary_config = self.config.get("primary") if isinstance(self.config.get("primary"), dict) else {}
        self.primary = build_tts_provider(primary_config)
        self.cached_fallback = CachedAudioTTSProvider(_first_enabled_cached_config(self.config))
        self.fallbacks = [
            build_tts_provider(fallback)
            for fallback in self.config.get("fallback", [])
            if isinstance(fallback, dict) and fallback.get("enabled") and fallback.get("provider") != "cached_audio"
        ]

    def synthesize(self, text: str, voice: str | None = None, audio_format: str = "wav") -> TTSResult:
        try:
            return self.primary.synthesize(text, voice=voice, audio_format=audio_format)
        except Exception as primary_error:
            print(f"TTS primary failed provider={self.primary.provider} error={primary_error}", flush=True)
            for provider in self.fallbacks:
                try:
                    return provider.synthesize(text, voice=voice, audio_format=audio_format)
                except Exception as fallback_error:
                    print(f"TTS fallback failed provider={provider.provider} error={fallback_error}", flush=True)
            return self.cached_fallback.synthesize(text)

    def get_cached_error_audio(self, name: str = "sorry_retry") -> TTSResult:
        return self.cached_fallback.get(name)

    def get_cached_audio_if_exists(self, name: str | None) -> TTSResult | None:
        if not name:
            return None
        return self.cached_fallback.get_if_exists(name)


def build_tts_provider(config: dict[str, Any]) -> TTSProvider:
    provider = str(config.get("provider") or "mock").strip().lower()
    if provider == "siliconflow_tts":
        return SiliconFlowTTSProvider(config)
    if provider == "cached_audio":
        return CachedAudioTTSProvider(config)
    return LegacyTTSProvider(config)


def _first_enabled_cached_config(config: dict[str, Any]) -> dict[str, Any]:
    for fallback in config.get("fallback", []):
        if isinstance(fallback, dict) and fallback.get("enabled") and fallback.get("provider") == "cached_audio":
            return fallback
    return {"provider": "cached_audio", "voice": "sorry_retry", "enabled": True}


def get_tts_router() -> TTSRouter:
    return TTSRouter()
