from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class STTResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    language: str | None = None
    emotion: str | None = None
    event: str | None = None
    confidence: float | None = None
    raw: dict[str, Any] | None = None


class STTProvider:
    provider = "base"

    def transcribe(self, audio_path: Path, language: str = "zh") -> STTResult:
        raise NotImplementedError
