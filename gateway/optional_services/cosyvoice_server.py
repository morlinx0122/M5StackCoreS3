import math
import os
import struct
import sys
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


app = FastAPI(title="DeepNexus CosyVoice TTS Service", version="0.1.0")
OUTPUT_DIR = Path(os.getenv("COSYVOICE_OUTPUT_DIR", "app/static/audio/cosyvoice"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "default"
    sample_rate: int = 22050
    format: str = "wav"
    prompt_text: str | None = None
    prompt_audio: str | None = None


class CosyVoiceEngine:
    def __init__(self) -> None:
        self.model: Any | None = None
        self.model_path = os.getenv("COSYVOICE_MODEL", "iic/CosyVoice2-0.5B")
        self.mode = os.getenv("COSYVOICE_SERVER_MODE", "placeholder").lower()
        self.repo_dir = os.getenv("COSYVOICE_REPO", "").strip()
        self.prompt_text = os.getenv("COSYVOICE_PROMPT_TEXT", "").strip()
        self.prompt_audio = os.getenv("COSYVOICE_PROMPT_AUDIO", "").strip()

    def load(self) -> None:
        if self.model is not None:
            return
        if self.mode == "placeholder":
            self.model = "placeholder"
            return

        if self.repo_dir:
            repo_path = Path(self.repo_dir)
            sys.path.insert(0, str(repo_path))
            sys.path.insert(0, str(repo_path / "third_party" / "Matcha-TTS"))

        try:
            from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2
        except ImportError as exc:
            raise RuntimeError(
                "CosyVoice runtime is not importable. Clone the CosyVoice repo, "
                "install its requirements, and set COSYVOICE_REPO to the repo path."
            ) from exc

        if self.mode == "cosyvoice2_zero_shot":
            self.model = CosyVoice2(self.model_path, load_jit=False, load_trt=False, load_vllm=False, fp16=False)
            return

        if self.mode == "cosyvoice_sft":
            self.model = CosyVoice(self.model_path, load_jit=False, load_trt=False, fp16=False)
            return

        raise RuntimeError(f"Unsupported COSYVOICE_SERVER_MODE: {self.mode}")

    def synthesize(self, request: SynthesizeRequest) -> Path:
        self.load()
        if self.model == "placeholder":
            return write_placeholder_wav(request.text, request.sample_rate)

        if self.mode == "cosyvoice2_zero_shot":
            return self._synthesize_zero_shot(request)

        if self.mode == "cosyvoice_sft":
            return self._synthesize_sft(request)

        raise RuntimeError(f"Unsupported COSYVOICE_SERVER_MODE: {self.mode}")

    def _synthesize_zero_shot(self, request: SynthesizeRequest) -> Path:
        prompt_text = request.prompt_text or self.prompt_text
        prompt_audio = request.prompt_audio or self.prompt_audio
        if not prompt_text or not prompt_audio:
            raise RuntimeError(
                "CosyVoice2 zero-shot mode requires COSYVOICE_PROMPT_TEXT and COSYVOICE_PROMPT_AUDIO, "
                "or prompt_text and prompt_audio in the request."
            )

        try:
            import torchaudio
        except ImportError as exc:
            raise RuntimeError("CosyVoice2 zero-shot mode requires torchaudio and CosyVoice utils.") from exc

        generator = self.model.inference_zero_shot(
            request.text,
            prompt_text,
            prompt_audio,
            stream=False,
        )
        output = next(generator)
        return save_cosyvoice_output(output, self.model.sample_rate, torchaudio)

    def _synthesize_sft(self, request: SynthesizeRequest) -> Path:
        try:
            import torchaudio
        except ImportError as exc:
            raise RuntimeError("CosyVoice SFT mode requires torchaudio.") from exc

        generator = self.model.inference_sft(request.text, request.voice, stream=False)
        output = next(generator)
        return save_cosyvoice_output(output, self.model.sample_rate, torchaudio)


engine = CosyVoiceEngine()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "cosyvoice-tts",
        "model": engine.model_path,
        "mode": engine.mode,
        "loaded": engine.model is not None,
    }


@app.post("/synthesize")
def synthesize(request: SynthesizeRequest) -> FileResponse:
    if request.format.lower() != "wav":
        raise HTTPException(status_code=400, detail="Only wav format is supported.")

    started = perf_counter()
    wav_path = engine.synthesize(request)
    latency_ms = int((perf_counter() - started) * 1000)
    return FileResponse(
        wav_path,
        media_type="audio/wav",
        filename=wav_path.name,
        headers={"X-TTS-Latency-Ms": str(latency_ms)},
    )


def write_placeholder_wav(text: str, sample_rate: int) -> Path:
    duration_seconds = min(max(len(text) / 18.0, 0.6), 2.0)
    total_samples = int(sample_rate * duration_seconds)
    amplitude = 8000
    frequency = 660
    pcm = bytearray()
    for index in range(total_samples):
        value = int(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
        pcm += struct.pack("<h", value)

    wav_bytes = wav_from_pcm(bytes(pcm), sample_rate)
    output_path = OUTPUT_DIR / f"cosy_{uuid4().hex}.wav"
    output_path.write_bytes(wav_bytes)
    return output_path


def wav_from_pcm(pcm: bytes, sample_rate: int) -> bytes:
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


def save_cosyvoice_output(output: dict[str, Any], sample_rate: int, torchaudio) -> Path:
    speech = output.get("tts_speech")
    if speech is None:
        raise RuntimeError(f"CosyVoice output does not contain tts_speech: {output.keys()}")

    output_path = OUTPUT_DIR / f"cosy_{uuid4().hex}.wav"
    torchaudio.save(str(output_path), speech, sample_rate)
    return output_path
