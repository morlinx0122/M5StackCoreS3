from __future__ import annotations

import shutil
from pathlib import Path

from app.services.tts_router import get_tts_router


class TTSChunkService:
    def __init__(self) -> None:
        self.tts_router = get_tts_router()

    def cached_or_synthesize(self, text: str, cache_key: str | None = None):
        if cache_key:
            cached = self.tts_router.get_cached_audio_if_exists(cache_key)
            if cached is not None:
                return cached
        return self.tts_router.synthesize(text)

    def chunk_for_text(self, session_id: str, chunk_index: int, text: str, cache_key: str | None = None):
        result = self.cached_or_synthesize(text, cache_key)
        output_dir = Path("app/static/audio/reply")
        output_dir.mkdir(parents=True, exist_ok=True)
        chunk_name = f"{session_id}_chunk_{chunk_index:03d}.wav"
        chunk_path = output_dir / chunk_name
        if result.file_path.resolve() != chunk_path.resolve():
            shutil.copyfile(result.file_path, chunk_path)
        return result, f"/static/audio/reply/{chunk_name}", chunk_path
