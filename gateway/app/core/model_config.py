from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - runtime fallback for lean installs.
    yaml = None


DEFAULT_MODEL_CONFIG: dict[str, Any] = {
    "audio_chat": {
        "mode": "async_job",
        "pipeline": "stt_llm_tts",
        "default_language": "zh",
        "input_sample_rate": 16000,
        "output_format": "wav",
        "command_poll_mode": True,
    },
    "stt": {
        "router": "enabled",
        "primary": {
            "provider": "siliconflow_stt",
            "model": "FunAudioLLM/SenseVoiceSmall",
            "timeout_sec": 30,
        },
        "fallback": [],
        "final": {
            "provider": "siliconflow_stt",
            "model": "FunAudioLLM/SenseVoiceSmall",
            "enabled": True,
            "block_for_important_tasks": True,
        },
        "vad": {
            "device_side_vad": True,
            "gateway_vad": {
                "provider": "funasr_local",
                "model": "fsmn-vad",
                "enabled": True,
            },
        },
        "streaming": {
            "provider": "funasr_local",
            "model": "paraformer-zh-streaming",
            "enabled": True,
        },
    },
    "llm": {
        "router": "enabled",
        "primary": {
            "provider": "siliconflow",
            "model": "Qwen/Qwen3-8B",
            "timeout_sec": 4,
            "max_tokens": 80,
            "temperature": 0.3,
            "stream": True,
            "enable_thinking": False,
        },
        "voice_chat": {
            "provider": "siliconflow",
            "model": "Qwen/Qwen3-8B",
            "stream": True,
            "enable_thinking": False,
            "max_tokens": 80,
            "temperature": 0.3,
            "timeout_sec": 4,
        },
        "fallback": [
            {
                "provider": "siliconflow",
                "model": "Qwen/Qwen3-14B",
                "stream": True,
                "enable_thinking": False,
                "timeout_sec": 5,
                "enabled": True,
            },
            {
                "provider": "siliconflow",
                "model": "deepseek-ai/DeepSeek-V3.2",
                "stream": True,
                "timeout_sec": 6,
                "enabled": True,
            },
        ],
    },
    "tts": {
        "router": "enabled",
        "primary": {
            "provider": "siliconflow_tts",
            "model": "FunAudioLLM/CosyVoice2-0.5B",
            "voice": "FunAudioLLM/CosyVoice2-0.5B:alex",
            "mode": "sentence_chunk",
            "format": "wav",
            "timeout_sec": 8,
        },
        "cached_audio": {
            "enabled": True,
            "base_dir": "static/audio/system",
        },
        "fallback": [
            {
                "provider": "cached_audio",
                "voice": "sorry_retry",
                "enabled": True,
            }
        ],
    },
    "voice_realtime": {
        "enabled": True,
        "mode": "realtime_uplink_chunked_downlink",
        "fallback_http_async": True,
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "format": "pcm_s16le",
        "frame_ms": 20,
    },
    "fast_intent": {
        "enabled": True,
        "bypass_llm": True,
        "bypass_tts_when_cached": True,
    },
    "core_s3": {
        "playback_mode": "chunk_queue",
        "ws_reconnect": True,
        "http_fallback": True,
    },
    "device_command": {
        "play_audio": {
            "expire_sec": 120,
            "retry_limit": 3,
        }
    },
    "job": {
        "expire_sec": 300,
        "save_step_latency": True,
        "save_model_payload": True,
    },
}


def load_model_config() -> dict[str, Any]:
    config = copy.deepcopy(DEFAULT_MODEL_CONFIG)
    config_path = Path(os.getenv("MODEL_CONFIG_PATH", "config.yaml"))
    if config_path.exists() and yaml is not None:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            _deep_merge(config, loaded)

    _apply_env_overrides(config)
    return config


def model_section(name: str) -> dict[str, Any]:
    section = load_model_config().get(name, {})
    return section if isinstance(section, dict) else {}


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def _apply_env_overrides(config: dict[str, Any]) -> None:
    stt_primary = config.setdefault("stt", {}).setdefault("primary", {})
    stt_primary["provider"] = os.getenv("STT_PROVIDER", stt_primary.get("provider", "siliconflow_stt"))
    stt_primary["model"] = os.getenv("SILICONFLOW_STT_MODEL", stt_primary.get("model", "FunAudioLLM/SenseVoiceSmall"))
    if os.getenv("SILICONFLOW_STT_TIMEOUT_SECONDS"):
        stt_primary["timeout_sec"] = int(float(os.getenv("SILICONFLOW_STT_TIMEOUT_SECONDS", "30")))

    llm_primary = config.setdefault("llm", {}).setdefault("primary", {})
    llm_primary["provider"] = os.getenv("LLM_PROVIDER", llm_primary.get("provider", "siliconflow"))
    llm_primary["model"] = os.getenv("SILICONFLOW_LLM_MODEL", llm_primary.get("model", "Qwen/Qwen3-8B"))
    llm_voice = config.setdefault("llm", {}).setdefault("voice_chat", {})
    llm_voice["provider"] = os.getenv("LLM_PROVIDER", llm_voice.get("provider", "siliconflow"))
    llm_voice["model"] = os.getenv("SILICONFLOW_VOICE_LLM_MODEL", llm_voice.get("model", llm_primary["model"]))
    fallback_provider = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()
    if fallback_provider:
        config["llm"]["fallback"] = [
            {
                "provider": fallback_provider,
                "model": os.getenv(f"{fallback_provider.upper()}_LLM_MODEL", fallback_provider),
                "enabled": True,
            }
        ]

    tts_primary = config.setdefault("tts", {}).setdefault("primary", {})
    tts_primary["provider"] = os.getenv("TTS_PROVIDER", tts_primary.get("provider", "siliconflow_tts"))
    tts_primary["model"] = os.getenv("SILICONFLOW_TTS_MODEL", tts_primary.get("model", "FunAudioLLM/CosyVoice2-0.5B"))
    tts_primary["voice"] = os.getenv(
        "SILICONFLOW_TTS_VOICE",
        tts_primary.get("voice", "FunAudioLLM/CosyVoice2-0.5B:alex"),
    )
    if os.getenv("SILICONFLOW_TTS_TIMEOUT_SECONDS"):
        tts_primary["timeout_sec"] = int(float(os.getenv("SILICONFLOW_TTS_TIMEOUT_SECONDS", "60")))
