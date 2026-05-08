import os
import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import httpx

from app.services.openai_common import openai_client


@dataclass(frozen=True)
class STTResult:
    text: str
    provider: str
    latency_ms: int
    confidence: float | None = None


class STTService:
    provider = "base"

    def transcribe(self, audio_path: Path) -> STTResult:
        raise NotImplementedError


class MockSTTService(STTService):
    provider = "mock"

    def transcribe(self, audio_path: Path) -> STTResult:
        started = perf_counter()
        default_text = "这是一次语音上传测试，音频已经成功到达 Gateway。"
        text = os.getenv("MOCK_STT_TEXT", default_text)
        latency_ms = int((perf_counter() - started) * 1000)
        return STTResult(
            text=text,
            provider=self.provider,
            latency_ms=latency_ms,
            confidence=1.0,
        )


class OpenAISTTService(STTService):
    provider = "openai"

    def __init__(self) -> None:
        self.client = openai_client()
        self.model = os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")
        self.language = os.getenv("OPENAI_STT_LANGUAGE", "zh")

    def transcribe(self, audio_path: Path) -> STTResult:
        started = perf_counter()
        with audio_path.open("rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                language=self.language,
            )
        latency_ms = int((perf_counter() - started) * 1000)
        return STTResult(
            text=getattr(transcript, "text", str(transcript)),
            provider=self.provider,
            latency_ms=latency_ms,
        )


class SenseVoiceHTTPSTTService(STTService):
    provider = "sensevoice_http"

    def __init__(self) -> None:
        self.url = os.getenv("SENSEVOICE_URL", "http://127.0.0.1:9001/transcribe")
        self.language = os.getenv("SENSEVOICE_LANGUAGE", "zh")
        self.timeout_seconds = float(os.getenv("SENSEVOICE_TIMEOUT_SECONDS", "60"))

    def transcribe(self, audio_path: Path) -> STTResult:
        started = perf_counter()
        with audio_path.open("rb") as audio_file:
            response = httpx.post(
                self.url,
                data={"language": self.language},
                files={"audio": (audio_path.name, audio_file, "audio/wav")},
                timeout=self.timeout_seconds,
                trust_env=False,
            )
        response.raise_for_status()
        payload = response.json()
        latency_ms = int((perf_counter() - started) * 1000)
        return STTResult(
            text=clean_sensevoice_text(self._extract_text(payload)),
            provider=self.provider,
            latency_ms=latency_ms,
            confidence=self._extract_confidence(payload),
        )

    def _extract_text(self, payload: dict) -> str:
        candidates = [
            payload.get("text"),
            payload.get("transcript"),
            payload.get("result", {}).get("text") if isinstance(payload.get("result"), dict) else None,
            payload.get("data", {}).get("text") if isinstance(payload.get("data"), dict) else None,
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        raise ValueError(f"SenseVoice response does not contain text: {payload}")

    def _extract_confidence(self, payload: dict) -> float | None:
        confidence = payload.get("confidence")
        if confidence is None and isinstance(payload.get("result"), dict):
            confidence = payload["result"].get("confidence")
        if confidence is None and isinstance(payload.get("data"), dict):
            confidence = payload["data"].get("confidence")
        return float(confidence) if confidence is not None else None


class SiliconFlowSTTService(STTService):
    provider = "siliconflow_stt"

    def __init__(self) -> None:
        api_key = os.getenv("SILICONFLOW_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("SILICONFLOW_API_KEY is required when using siliconflow_stt.")

        self.api_key = api_key
        self.base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
        self.model = os.getenv("SILICONFLOW_STT_MODEL", "FunAudioLLM/SenseVoiceSmall")
        self.timeout_seconds = float(os.getenv("SILICONFLOW_STT_TIMEOUT_SECONDS", "60"))

    def transcribe(self, audio_path: Path) -> STTResult:
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
        latency_ms = int((perf_counter() - started) * 1000)
        return STTResult(
            text=clean_sensevoice_text(str(payload.get("text") or "")),
            provider=self.provider,
            latency_ms=latency_ms,
        )


def get_stt_service() -> STTService:
    provider = os.getenv("STT_PROVIDER", "mock").strip().lower()
    if provider == "mock":
        return MockSTTService()
    if provider == "sensevoice_http":
        return SenseVoiceHTTPSTTService()
    if provider == "siliconflow_stt":
        return SiliconFlowSTTService()
    if provider == "openai":
        return OpenAISTTService()

    # Keep the first version explicit: unsupported providers should fail closed
    # instead of silently pretending transcription happened.
    raise ValueError(f"Unsupported STT_PROVIDER: {provider}")


def clean_sensevoice_text(text: str) -> str:
    cleaned = re.sub(r"<\|[^|]+?\|>", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()
