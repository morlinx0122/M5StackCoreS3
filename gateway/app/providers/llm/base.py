from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    emotion: str | None = None
    face_state: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str = "stop"
    raw: dict[str, Any] | None = None


class LLMProvider:
    provider = "base"
    model = "base"

    def chat(self, user_text: str, scenario: str = "deskbot", device_id: str | None = None) -> LLMResult:
        raise NotImplementedError
