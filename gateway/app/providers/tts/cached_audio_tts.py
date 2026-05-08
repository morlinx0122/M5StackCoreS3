from __future__ import annotations

import math
import struct
from pathlib import Path
from time import perf_counter
from typing import Any

from app.providers.tts.base import TTSProvider, TTSResult


class CachedAudioTTSProvider(TTSProvider):
    provider = "cached_audio"
    model = "cached_audio"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.voice = str(cfg.get("voice") or "sorry_retry")
        self.sample_rate = 16000

    def synthesize(self, text: str, voice: str | None = None, audio_format: str = "wav") -> TTSResult:
        return self.get(voice or self.voice)

    def get_if_exists(self, name: str) -> TTSResult | None:
        file_path = Path("app/static/audio/system") / f"{Path(name).stem}.wav"
        if not file_path.exists():
            return None
        return self._result(file_path, Path(name).stem, 0)

    def get(self, name: str = "sorry_retry") -> TTSResult:
        started = perf_counter()
        output_dir = Path("app/static/audio/system")
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"{Path(name).stem}.wav"
        if not file_path.exists():
            file_path.write_bytes(_wav_bytes(_tone_pcm(self.sample_rate, 0.65, 440), self.sample_rate))
        return self._result(file_path, Path(name).stem, int((perf_counter() - started) * 1000))

    def _result(self, file_path: Path, voice: str, latency_ms: int) -> TTSResult:
        return TTSResult(
            audio_url=f"/static/audio/system/{file_path.name}",
            file_path=file_path,
            provider=self.provider,
            model=self.model,
            voice=voice,
            latency_ms=latency_ms,
            size_bytes=file_path.stat().st_size,
            sample_rate=self.sample_rate,
        )


def _tone_pcm(sample_rate: int, duration_seconds: float, frequency: float) -> bytes:
    total_samples = int(sample_rate * duration_seconds)
    amplitude = 6500
    samples = bytearray()
    for index in range(total_samples):
        value = int(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
        samples += struct.pack("<h", value)
    return bytes(samples)


def _wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
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
