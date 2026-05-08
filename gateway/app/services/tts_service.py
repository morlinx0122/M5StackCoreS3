import base64
import math
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx
import soundfile as sf

from app.services.openai_common import openai_client


@dataclass(frozen=True)
class TTSResult:
    provider: str
    audio_url: str
    file_path: Path
    latency_ms: int
    size_bytes: int
    sample_rate: int


class TTSService:
    provider = "base"

    def synthesize(self, text: str) -> TTSResult:
        raise NotImplementedError


class MockTTSService(TTSService):
    provider = "mock"

    def synthesize(self, text: str) -> TTSResult:
        started = perf_counter()
        sample_rate = int(os.getenv("MOCK_TTS_SAMPLE_RATE", "16000"))
        duration_seconds = float(os.getenv("MOCK_TTS_DURATION_SECONDS", "0.8"))
        frequency = float(os.getenv("MOCK_TTS_FREQUENCY", "880"))

        output_dir = Path("app/static/audio/reply")
        output_dir.mkdir(parents=True, exist_ok=True)
        asset_id = f"tts_{uuid4().hex}"
        file_path = output_dir / f"{asset_id}.wav"
        pcm = self._tone_pcm(sample_rate, duration_seconds, frequency)
        wav_bytes = self._wav_bytes(pcm, sample_rate)
        file_path.write_bytes(wav_bytes)

        return TTSResult(
            provider=self.provider,
            audio_url=f"/static/audio/reply/{asset_id}.wav",
            file_path=file_path,
            latency_ms=int((perf_counter() - started) * 1000),
            size_bytes=len(wav_bytes),
            sample_rate=sample_rate,
        )

    def _tone_pcm(self, sample_rate: int, duration_seconds: float, frequency: float) -> bytes:
        total_samples = int(sample_rate * duration_seconds)
        amplitude = 8000
        samples = bytearray()
        for index in range(total_samples):
            value = int(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
            samples += struct.pack("<h", value)
        return bytes(samples)

    def _wav_bytes(self, pcm: bytes, sample_rate: int) -> bytes:
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


class OpenAITTSService(TTSService):
    provider = "openai"

    def __init__(self) -> None:
        self.client = openai_client()
        self.model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
        self.voice = os.getenv("OPENAI_TTS_VOICE", "alloy")
        self.sample_rate = int(os.getenv("OPENAI_TTS_SAMPLE_RATE", "24000"))

    def synthesize(self, text: str) -> TTSResult:
        started = perf_counter()
        output_dir = Path("app/static/audio/reply")
        output_dir.mkdir(parents=True, exist_ok=True)
        asset_id = f"tts_{uuid4().hex}"
        file_path = output_dir / f"{asset_id}.wav"

        response = self.client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=text,
            response_format="wav",
        )
        self._write_response(file_path, response)

        return TTSResult(
            provider=self.provider,
            audio_url=f"/static/audio/reply/{asset_id}.wav",
            file_path=file_path,
            latency_ms=int((perf_counter() - started) * 1000),
            size_bytes=file_path.stat().st_size,
            sample_rate=self.sample_rate,
        )

    def _write_response(self, file_path: Path, response) -> None:
        if hasattr(response, "write_to_file"):
            response.write_to_file(file_path)
            return

        data = response.read() if hasattr(response, "read") else bytes(response)
        file_path.write_bytes(data)


class CosyVoiceHTTPTTSService(TTSService):
    provider = "cosyvoice_http"

    def __init__(self) -> None:
        self.url = os.getenv("COSYVOICE_URL", "http://127.0.0.1:9002/synthesize")
        self.voice = os.getenv("COSYVOICE_VOICE", "default")
        self.sample_rate = int(os.getenv("COSYVOICE_SAMPLE_RATE", "22050"))
        self.timeout_seconds = float(os.getenv("COSYVOICE_TIMEOUT_SECONDS", "120"))

    def synthesize(self, text: str) -> TTSResult:
        started = perf_counter()
        payload = {
            "text": text,
            "voice": self.voice,
            "sample_rate": self.sample_rate,
            "format": "wav",
        }
        response = self._post_with_retry(payload)

        output_dir = Path("app/static/audio/reply")
        output_dir.mkdir(parents=True, exist_ok=True)
        asset_id = f"tts_{uuid4().hex}"
        file_path = output_dir / f"{asset_id}.wav"
        self._save_response(response, file_path)

        return TTSResult(
            provider=self.provider,
            audio_url=f"/static/audio/reply/{asset_id}.wav",
            file_path=file_path,
            latency_ms=int((perf_counter() - started) * 1000),
            size_bytes=file_path.stat().st_size,
            sample_rate=self.sample_rate,
        )

    def _post_with_retry(self, payload: dict) -> httpx.Response:
        last_error: httpx.HTTPStatusError | None = None
        for attempt in range(1, 3):
            response = httpx.post(
                self.url,
                json=payload,
                timeout=self.timeout_seconds,
                trust_env=False,
            )
            try:
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                last_error = exc
                detail = response.text[:500]
                print(
                    "CosyVoice HTTP failed "
                    f"attempt={attempt} status={response.status_code} "
                    f"text_len={len(payload.get('text', ''))} detail={detail}",
                    flush=True,
                )
                if response.status_code < 500 or attempt == 2:
                    raise
                time.sleep(1)

        raise last_error if last_error is not None else RuntimeError("CosyVoice HTTP request failed")

    def _save_response(self, response: httpx.Response, file_path: Path) -> None:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = response.json()
            audio_url = payload.get("audio_url") or payload.get("url")
            if not audio_url:
                raise ValueError(f"CosyVoice JSON response does not contain audio_url: {payload}")
            audio_response = httpx.get(audio_url, timeout=self.timeout_seconds, trust_env=False)
            audio_response.raise_for_status()
            self._write_pcm16_wav(audio_response.content, file_path)
            return

        self._write_pcm16_wav(response.content, file_path)

    def _write_pcm16_wav(self, wav_bytes: bytes, file_path: Path) -> None:
        temp_path = file_path.with_suffix(".source.wav")
        temp_path.write_bytes(wav_bytes)
        try:
            audio, sample_rate = sf.read(temp_path, always_2d=True)
            sf.write(file_path, audio, sample_rate, subtype="PCM_16")
        finally:
            temp_path.unlink(missing_ok=True)


class SiliconFlowTTSService(TTSService):
    provider = "siliconflow_tts"

    def __init__(self) -> None:
        api_key = os.getenv("SILICONFLOW_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("SILICONFLOW_API_KEY is required when using siliconflow_tts.")

        self.api_key = api_key
        self.base_url = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/")
        self.model = os.getenv("SILICONFLOW_TTS_MODEL", "FunAudioLLM/CosyVoice2-0.5B")
        self.voice = os.getenv("SILICONFLOW_TTS_VOICE", "FunAudioLLM/CosyVoice2-0.5B:alex")
        self.sample_rate = int(os.getenv("SILICONFLOW_TTS_SAMPLE_RATE", "24000"))
        self.gain = float(os.getenv("SILICONFLOW_TTS_GAIN", "0"))
        self.timeout_seconds = float(os.getenv("SILICONFLOW_TTS_TIMEOUT_SECONDS", "60"))

    def synthesize(self, text: str) -> TTSResult:
        started = perf_counter()
        response = httpx.post(
            f"{self.base_url}/audio/speech",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "input": text,
                "voice": self.voice,
                "response_format": "wav",
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
        self._write_pcm16_wav(response.content, file_path)

        return TTSResult(
            provider=self.provider,
            audio_url=f"/static/audio/reply/{asset_id}.wav",
            file_path=file_path,
            latency_ms=int((perf_counter() - started) * 1000),
            size_bytes=file_path.stat().st_size,
            sample_rate=self.sample_rate,
        )

    def _write_pcm16_wav(self, wav_bytes: bytes, file_path: Path) -> None:
        temp_path = file_path.with_suffix(".source.wav")
        temp_path.write_bytes(wav_bytes)
        try:
            audio, sample_rate = sf.read(temp_path, always_2d=True)
            sf.write(file_path, audio, sample_rate, subtype="PCM_16")
        finally:
            temp_path.unlink(missing_ok=True)


class MiMoTTSService(TTSService):
    provider = "mimo_tts"

    def __init__(self) -> None:
        api_key = os.getenv("MIMO_API_KEY", "").strip() or os.getenv("XIAOMI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("MIMO_API_KEY or XIAOMI_API_KEY is required when using mimo_tts.")

        self.api_key = api_key
        self.base_url = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1").rstrip("/")
        self.model = os.getenv("MIMO_TTS_MODEL", "mimo-v2.5-tts")
        self.voice = os.getenv("MIMO_TTS_VOICE", "mimo_default").strip()
        self.style_prompt = os.getenv("MIMO_TTS_STYLE_PROMPT", "").strip()
        self.sample_rate = int(os.getenv("MIMO_TTS_SAMPLE_RATE", "24000"))
        self.timeout_seconds = float(os.getenv("MIMO_TTS_TIMEOUT_SECONDS", "60"))

    def synthesize(self, text: str) -> TTSResult:
        started = perf_counter()
        messages = []
        if self.style_prompt:
            messages.append({"role": "user", "content": self.style_prompt})
        messages.append({"role": "assistant", "content": text})

        payload = {
            "model": self.model,
            "messages": messages,
            "audio": {
                "format": "wav",
            },
        }
        if self.voice:
            payload["audio"]["voice"] = self.voice

        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "api-key": self.api_key,
            },
            json=payload,
            timeout=self.timeout_seconds,
            trust_env=False,
        )
        response.raise_for_status()

        output_dir = Path("app/static/audio/reply")
        output_dir.mkdir(parents=True, exist_ok=True)
        asset_id = f"tts_{uuid4().hex}"
        file_path = output_dir / f"{asset_id}.wav"
        self._save_response_audio(response.json(), file_path)

        return TTSResult(
            provider=self.provider,
            audio_url=f"/static/audio/reply/{asset_id}.wav",
            file_path=file_path,
            latency_ms=int((perf_counter() - started) * 1000),
            size_bytes=file_path.stat().st_size,
            sample_rate=self.sample_rate,
        )

    def _save_response_audio(self, payload: dict, file_path: Path) -> None:
        try:
            audio_data = payload["choices"][0]["message"]["audio"]["data"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"MiMo TTS response does not contain audio data: {payload}") from exc

        wav_bytes = base64.b64decode(audio_data)
        temp_path = file_path.with_suffix(".source.wav")
        temp_path.write_bytes(wav_bytes)
        try:
            audio, sample_rate = sf.read(temp_path, always_2d=True)
            sf.write(file_path, audio, sample_rate, subtype="PCM_16")
        finally:
            temp_path.unlink(missing_ok=True)


def get_tts_service() -> TTSService:
    provider = os.getenv("TTS_PROVIDER", "mock").strip().lower()
    if provider == "mock":
        return MockTTSService()
    if provider == "cosyvoice_http":
        return CosyVoiceHTTPTTSService()
    if provider == "siliconflow_tts":
        return SiliconFlowTTSService()
    if provider == "mimo_tts":
        return MiMoTTSService()
    if provider == "openai":
        return OpenAITTSService()

    raise ValueError(f"Unsupported TTS_PROVIDER: {provider}")
