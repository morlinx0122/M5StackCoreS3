from __future__ import annotations

import io
import os
import re
import struct
from pathlib import Path
from typing import Any

import httpx

from app.services.stt_router import get_stt_router


_SENSEVOICE_TAG_RE = re.compile(r"<\|[^|>]*\|>")
# Anything in this set is considered "no real content" — pure punctuation,
# whitespace, or filler exclamations from a noisy mic.
_FILLER_CHARS = set("。，,.!！？?；;：:、…—-~ \t\n\r\u3000")


def _clean_sensevoice_text(text: str) -> str:
    """Strip SenseVoice control tags and trim whitespace."""
    if not text:
        return ""
    return _SENSEVOICE_TAG_RE.sub("", text).strip()


def is_meaningful_stt(text: str) -> bool:
    """True only if cleaned text has at least one non-filler character."""
    cleaned = _clean_sensevoice_text(text)
    if not cleaned:
        return False
    return any(ch not in _FILLER_CHARS for ch in cleaned)


def _pcm_to_wav_bytes(pcm: bytes, sample_rate: int = 16000) -> bytes:
    channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    header = bytearray()
    header += b"RIFF"
    header += struct.pack("<I", 36 + len(pcm))
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample)
    header += b"data"
    header += struct.pack("<I", len(pcm))
    return bytes(header) + pcm


class StreamingSTTService:
    def __init__(self) -> None:
        self.base_url = os.getenv("FUNASR_REALTIME_URL", "http://127.0.0.1:9003").rstrip("/")
        self.timeout_seconds = float(os.getenv("FUNASR_REALTIME_TIMEOUT_SECONDS", "10"))
        self.partial_min_bytes = int(os.getenv("FUNASR_PARTIAL_MIN_BYTES", str(16000 * 2)))

    def partial_from_pcm(self, pcm_size_bytes: int) -> str:
        if pcm_size_bytes < 16000:
            return ""
        seconds = pcm_size_bytes / 2 / 16000
        return f"正在听，大约 {seconds:.1f} 秒音频。"

    def partial_from_wav(self, wav_path: Path, pcm_size_bytes: int) -> dict[str, Any] | None:
        if pcm_size_bytes < self.partial_min_bytes:
            return None
        try:
            with wav_path.open("rb") as audio_file:
                response = httpx.post(
                    f"{self.base_url}/partial",
                    data={"is_final": "false"},
                    files={"audio": (wav_path.name, audio_file, "audio/wav")},
                    timeout=self.timeout_seconds,
                    trust_env=False,
                )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            print(f"FunASR partial unavailable: {exc}", flush=True)
            return None
        text = str(payload.get("text") or "").strip()
        if not text:
            return None
        return payload

    def partial_from_pcm_bytes(self, pcm: bytes, sample_rate: int = 16000, is_final: bool = False) -> dict[str, Any] | None:
        if len(pcm) < self.partial_min_bytes:
            return None
        wav = _pcm_to_wav_bytes(pcm, sample_rate)
        try:
            response = httpx.post(
                f"{self.base_url}/partial",
                data={"is_final": "true" if is_final else "false"},
                files={"audio": ("frame.wav", io.BytesIO(wav), "audio/wav")},
                timeout=self.timeout_seconds,
                trust_env=False,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            print(f"FunASR partial(pcm) unavailable: {exc}", flush=True)
            return None
        text = str(payload.get("text") or "").strip()
        if not text:
            return None
        return payload

    def sensevoice_from_pcm_bytes(self, pcm: bytes, sample_rate: int = 16000, language: str = "zh") -> dict[str, Any] | None:
        """Run SenseVoice (offline accurate) on a short PCM clip — used for wake-word detection."""
        if len(pcm) < self.partial_min_bytes:
            return None
        wav = _pcm_to_wav_bytes(pcm, sample_rate)
        try:
            response = httpx.post(
                f"{self.base_url}/final",
                data={"language": language},
                files={"audio": ("clip.wav", io.BytesIO(wav), "audio/wav")},
                timeout=max(self.timeout_seconds, 10.0),
                trust_env=False,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            print(f"FunASR sensevoice(pcm) unavailable: {exc}", flush=True)
            return None
        text = str(payload.get("text") or "").strip()
        if not text:
            return None
        return payload

    def final_from_wav(self, wav_path: Path):
        try:
            with wav_path.open("rb") as audio_file:
                response = httpx.post(
                    f"{self.base_url}/final",
                    data={"language": "zh"},
                    files={"audio": (wav_path.name, audio_file, "audio/wav")},
                    timeout=max(self.timeout_seconds, 30),
                    trust_env=False,
                )
            response.raise_for_status()
            payload = response.json()
            return _dict_to_result(payload)
        except Exception as exc:
            print(f"FunASR final unavailable, falling back to STT router: {exc}", flush=True)
        return get_stt_router().transcribe(wav_path, language="zh")


class _STTDictResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.text = _clean_sensevoice_text(str(payload.get("text") or ""))
        self.language = payload.get("language") or "zh"
        self.emotion = payload.get("emotion")
        self.event = payload.get("event")
        self.provider = str(payload.get("provider") or "funasr_local")
        self.model = str(payload.get("model") or "iic/SenseVoiceSmall")
        self.latency_ms = int(payload.get("latency_ms") or 0)
        self.confidence = payload.get("confidence")
        self.raw = payload.get("raw")


def _dict_to_result(payload: dict[str, Any]) -> _STTDictResult:
    return _STTDictResult(payload)
