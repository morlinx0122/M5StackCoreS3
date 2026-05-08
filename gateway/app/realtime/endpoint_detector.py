from __future__ import annotations

import io
import os
import struct
from dataclasses import dataclass
from pathlib import Path

import httpx


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


@dataclass(frozen=True)
class EndpointResult:
    speech_detected: bool
    speech_segments: list[list[int]]
    provider: str
    model: str
    latency_ms: int


class EndpointDetector:
    def __init__(self) -> None:
        self.base_url = os.getenv("FUNASR_REALTIME_URL", "http://127.0.0.1:9003").rstrip("/")
        self.timeout_seconds = float(os.getenv("FUNASR_REALTIME_TIMEOUT_SECONDS", "10"))

    def detect(self, wav_path: Path) -> EndpointResult | None:
        try:
            with wav_path.open("rb") as audio_file:
                response = httpx.post(
                    f"{self.base_url}/vad",
                    files={"audio": (wav_path.name, audio_file, "audio/wav")},
                    timeout=self.timeout_seconds,
                    trust_env=False,
                )
            response.raise_for_status()
        except Exception as exc:
            print(f"FunASR VAD unavailable: {exc}", flush=True)
            return None

        payload = response.json()
        return EndpointResult(
            speech_detected=bool(payload.get("speech_detected")),
            speech_segments=payload.get("speech_segments") or [],
            provider=str(payload.get("provider") or "funasr_local"),
            model=str(payload.get("model") or "fsmn-vad"),
            latency_ms=int(payload.get("latency_ms") or 0),
        )

    def detect_pcm_bytes(self, pcm: bytes, sample_rate: int = 16000) -> EndpointResult | None:
        if not pcm:
            return None
        wav = _pcm_to_wav_bytes(pcm, sample_rate)
        try:
            response = httpx.post(
                f"{self.base_url}/vad",
                files={"audio": ("frame.wav", io.BytesIO(wav), "audio/wav")},
                timeout=self.timeout_seconds,
                trust_env=False,
            )
            response.raise_for_status()
        except Exception as exc:
            print(f"FunASR VAD(pcm) unavailable: {exc}", flush=True)
            return None
        payload = response.json()
        return EndpointResult(
            speech_detected=bool(payload.get("speech_detected")),
            speech_segments=payload.get("speech_segments") or [],
            provider=str(payload.get("provider") or "funasr_local"),
            model=str(payload.get("model") or "fsmn-vad"),
            latency_ms=int(payload.get("latency_ms") or 0),
        )
