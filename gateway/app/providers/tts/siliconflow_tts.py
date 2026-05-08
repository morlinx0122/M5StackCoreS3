from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx
import soundfile as sf

from app.providers.tts.base import TTSProvider, TTSResult


class SiliconFlowTTSProvider(TTSProvider):
    provider = "siliconflow_tts"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        api_key = os.getenv("SILICONFLOW_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("SILICONFLOW_API_KEY is required when using siliconflow_tts.")

        self.api_key = api_key
        self.base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
        self.model = str(cfg.get("model") or os.getenv("SILICONFLOW_TTS_MODEL") or "FunAudioLLM/CosyVoice2-0.5B")
        self.voice = str(
            cfg.get("voice") or os.getenv("SILICONFLOW_TTS_VOICE") or "FunAudioLLM/CosyVoice2-0.5B:alex"
        )
        self.sample_rate = int(os.getenv("SILICONFLOW_TTS_SAMPLE_RATE", "24000"))
        self.gain = float(os.getenv("SILICONFLOW_TTS_GAIN", "0"))
        self.timeout_seconds = float(cfg.get("timeout_sec") or os.getenv("SILICONFLOW_TTS_TIMEOUT_SECONDS") or 60)

    def synthesize(self, text: str, voice: str | None = None, audio_format: str = "wav") -> TTSResult:
        started = perf_counter()
        selected_voice = voice or self.voice
        response = httpx.post(
            f"{self.base_url}/audio/speech",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "input": text,
                "voice": selected_voice,
                "response_format": audio_format,
                "sample_rate": self.sample_rate,
                "gain": self.gain,
            },
            timeout=self.timeout_seconds,
            trust_env=False,
        )
        response.raise_for_status()

        output_dir = Path("app/static/audio/reply")
        output_dir.mkdir(parents=True, exist_ok=True)
        asset_id = f"tts_{uuid4().hex}"
        file_path = output_dir / f"{asset_id}.wav"
        # SiliconFlow returns a WAV that uses a sentinel "infinite-length" chunk size
        # in its RIFF/data headers (2^31-128 frames), which breaks strict players
        # such as the CoreS3 audio player. We must rewrite the header to match the
        # actual byte length. Re-encoding via soundfile guarantees correctness.
        _write_pcm16_wav(response.content, file_path)
        return TTSResult(
            audio_url=f"/static/audio/reply/{asset_id}.wav",
            file_path=file_path,
            provider=self.provider,
            model=self.model,
            voice=selected_voice,
            latency_ms=int((perf_counter() - started) * 1000),
            size_bytes=file_path.stat().st_size,
            sample_rate=self.sample_rate,
        )


def _write_pcm16_wav(wav_bytes: bytes, file_path: Path) -> None:
    temp_path = file_path.with_suffix(".source.wav")
    temp_path.write_bytes(wav_bytes)
    try:
        audio, sample_rate = sf.read(temp_path, always_2d=True)
        sf.write(file_path, audio, sample_rate, subtype="PCM_16")
    finally:
        temp_path.unlink(missing_ok=True)
