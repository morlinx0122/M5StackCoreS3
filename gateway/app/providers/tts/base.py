from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TTSResult:
    audio_url: str
    file_path: Path
    provider: str
    model: str
    voice: str
    latency_ms: int
    size_bytes: int
    sample_rate: int
    raw: dict[str, Any] | None = None


class TTSProvider:
    provider = "base"

    def synthesize(self, text: str, voice: str | None = None, audio_format: str = "wav") -> TTSResult:
        raise NotImplementedError
