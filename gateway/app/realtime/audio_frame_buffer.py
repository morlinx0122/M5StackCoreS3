from __future__ import annotations

from pathlib import Path
from time import time
from uuid import uuid4
import struct


class AudioFrameBuffer:
    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self.frames: list[bytes] = []
        self.first_audio_at: float | None = None
        self.last_audio_at: float | None = None

    def append(self, frame: bytes) -> None:
        if not frame:
            return
        now = time()
        if self.first_audio_at is None:
            self.first_audio_at = now
        self.last_audio_at = now
        self.frames.append(frame)

    def clear(self) -> None:
        self.frames.clear()
        self.first_audio_at = None
        self.last_audio_at = None

    def to_wav_file(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"rt_{uuid4().hex}.wav"
        pcm = b"".join(self.frames)
        file_path.write_bytes(_wav_bytes(pcm, self.sample_rate))
        return file_path

    @property
    def size_bytes(self) -> int:
        return sum(len(frame) for frame in self.frames)


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
