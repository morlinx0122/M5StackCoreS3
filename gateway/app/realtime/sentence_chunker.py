from __future__ import annotations

import re


class SentenceChunker:
    def __init__(self, min_chars: int = 12, max_chars: int = 25) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.buffer = ""

    def push(self, text: str) -> list[str]:
        self.buffer += text
        chunks: list[str] = []
        while True:
            chunk = self._pop_chunk()
            if chunk is None:
                break
            chunks.append(chunk)
        return chunks

    def flush(self) -> str | None:
        cleaned = self.buffer.strip()
        self.buffer = ""
        return cleaned or None

    def _pop_chunk(self) -> str | None:
        if len(self.buffer) < self.min_chars:
            return None
        # First try strong sentence enders, then comma-class for faster TTFB.
        match = re.search(r"[。！？；\n]", self.buffer)
        if match and match.end() >= self.min_chars:
            chunk = self.buffer[: match.end()].strip()
            self.buffer = self.buffer[match.end() :]
            return chunk
        match = re.search(r"[，,、:：]", self.buffer)
        if match and match.end() >= self.min_chars:
            chunk = self.buffer[: match.end()].strip()
            self.buffer = self.buffer[match.end() :]
            return chunk
        if len(self.buffer) >= self.max_chars:
            chunk = self.buffer[: self.max_chars].strip()
            self.buffer = self.buffer[self.max_chars :]
            return chunk
        return None
