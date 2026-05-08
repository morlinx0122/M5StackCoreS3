from __future__ import annotations

from typing import Any

from app.core.model_config import model_section
from app.providers.llm.base import LLMProvider, LLMResult
from app.providers.llm.siliconflow_llm import SiliconFlowLLMProvider
from app.services.llm_service import build_llm_service


class LegacyLLMProvider(LLMProvider):
    def __init__(self, config: dict[str, Any]) -> None:
        self.provider = str(config.get("provider") or "mock").strip().lower()
        self.service = build_llm_service(self.provider)
        self.model = str(config.get("model") or getattr(self.service, "model", self.provider))

    def chat(self, user_text: str, scenario: str = "deskbot", device_id: str | None = None) -> LLMResult:
        result = self.service.chat(user_text=user_text, scenario=scenario)
        return LLMResult(
            text=result.text,
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            finish_reason=result.finish_reason,
            emotion=getattr(result, "emotion", None),
            face_state=getattr(result, "face_state", None),
        )


class LLMRouter:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or model_section("llm")
        voice_config = self.config.get("voice_chat") if isinstance(self.config.get("voice_chat"), dict) else None
        primary_config = voice_config or (self.config.get("primary") if isinstance(self.config.get("primary"), dict) else {})
        self.primary = build_llm_provider(primary_config)
        self.fallbacks = [
            build_llm_provider(fallback)
            for fallback in self.config.get("fallback", [])
            if isinstance(fallback, dict) and fallback.get("enabled")
        ]

    def chat(self, user_text: str, scenario: str = "deskbot", device_id: str | None = None) -> LLMResult:
        try:
            return self.primary.chat(user_text=user_text, scenario=scenario, device_id=device_id)
        except Exception as primary_error:
            for provider in self.fallbacks:
                try:
                    return provider.chat(user_text=user_text, scenario=scenario, device_id=device_id)
                except Exception as fallback_error:
                    print(f"LLM fallback failed provider={provider.provider} error={fallback_error}", flush=True)
            raise primary_error


def build_llm_provider(config: dict[str, Any]) -> LLMProvider:
    provider = str(config.get("provider") or "mock").strip().lower()
    if provider == "siliconflow":
        return SiliconFlowLLMProvider(config)
    return LegacyLLMProvider(config)


def get_llm_router() -> LLMRouter:
    return LLMRouter()
