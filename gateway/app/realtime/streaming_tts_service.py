from __future__ import annotations

from app.services.tts_router import get_tts_router


class StreamingTTSService:
    def synthesize_chunk(self, text: str):
        return get_tts_router().synthesize(text)
