from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any

from openai import OpenAI

from app.providers.llm.base import LLMProvider, LLMResult
from app.services.llm_service import current_context


class SiliconFlowLLMProvider(LLMProvider):
    provider = "siliconflow"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        api_key = os.getenv("SILICONFLOW_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("SILICONFLOW_API_KEY is required when using siliconflow.")

        self.model = str(cfg.get("model") or os.getenv("SILICONFLOW_LLM_MODEL") or "stepfun-ai/Step-3.5-Flash")
        self.timeout_seconds = float(cfg.get("timeout_sec") or os.getenv("SILICONFLOW_LLM_TIMEOUT_SECONDS") or 60)
        self.max_tokens = int(cfg.get("max_tokens") or os.getenv("SILICONFLOW_LLM_MAX_TOKENS") or 80)
        self.temperature = float(cfg.get("temperature") or os.getenv("SILICONFLOW_LLM_TEMPERATURE") or 0.3)
        self.enable_thinking = bool(cfg.get("enable_thinking", False))
        self.client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
            timeout=self.timeout_seconds,
        )
        self.instructions = os.getenv(
            "LLM_SYSTEM_PROMPT",
            "你是一个温和、简洁、可靠的桌面 AI 机器人助理。回答要自然，适合通过语音朗读。",
        )

    def chat(self, user_text: str, scenario: str = "deskbot", device_id: str | None = None) -> LLMResult:
        started = perf_counter()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{self.instructions}\n{current_context()}\n"
                        "你是 DeepNexus DeskBot 的桌面语音机器人助手。"
                        "你的回答会被直接转成语音播放，所以必须："
                        "用自然口语中文回答；默认只回答一句话；不超过 40 个中文字；"
                        "不要 Markdown；不要列表；不要解释过程；能确认就直接确认；"
                        "如果用户只是闲聊，温和简短回应；如果需要执行工具，只返回简洁确认语。"
                        "请只输出 JSON："
                        "{\"assistant_text\":\"...\",\"emotion\":\"neutral|happy|sorry|thinking|concerned\","
                        "\"face_state\":\"IDLE|SPEAKING|SPEAKING_HAPPY|ERROR|THINKING\"}"
                    ),
                },
                {"role": "user", "content": f"场景：{scenario}\n设备：{device_id or ''}\n用户：{user_text}"},
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            extra_body={"enable_thinking": self.enable_thinking},
        )
        message = response.choices[0].message
        content = (message.content or "").strip()
        parsed = _parse_structured_reply(content)
        usage = getattr(response, "usage", None)
        return LLMResult(
            text=parsed["assistant_text"],
            emotion=parsed.get("emotion"),
            face_state=parsed.get("face_state"),
            provider=self.provider,
            model=self.model,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            latency_ms=int((perf_counter() - started) * 1000),
            finish_reason=response.choices[0].finish_reason or "stop",
            raw={"content": content},
        )


_VOICE_STREAM_SYSTEM_PROMPT = (
    "你是桌面语音机器人。回答会被语音播放。\n"
    "必须以 [emo:E][face:F] 开头，E\u2208{neutral|happy|sorry|thinking|concerned}，F\u2208{IDLE|SPEAKING|SPEAKING_HAPPY|ERROR|THINKING}。\n"
    "标签后立刻接正文：自然口语中文，不超过 60 字，无 Markdown，无列表，无解释。\n"
    "例：[emo:happy][face:SPEAKING_HAPPY]好啊，今天天气真不错！"
)


def stream_chat(
    self,  # type: ignore[misc]
    user_text: str,
    scenario: str = "deskbot",
    device_id: str | None = None,
):
    """Real streaming generator. Yields (text_token, LLMResult) tuples.
    First-token result has empty text; emotion/face_state are filled once tags are parsed.
    """
    import re as _re
    started = perf_counter()
    response = self.client.chat.completions.create(
        model=self.model,
        messages=[
            {
                "role": "system",
                "content": f"{_VOICE_STREAM_SYSTEM_PROMPT}\n上下文：{current_context()}",
            },
            {"role": "user", "content": f"场景：{scenario}\n设备：{device_id or ''}\n用户：{user_text}"},
        ],
        max_tokens=self.max_tokens,
        temperature=self.temperature,
        stream=True,
        extra_body={"enable_thinking": self.enable_thinking},
    )

    buffer = ""
    tags_done = False
    emotion = "neutral"
    face_state = "SPEAKING"
    tag_pattern = _re.compile(r"^\s*\[emo:([a-zA-Z_]+)\]\s*\[face:([a-zA-Z_]+)\]\s*")

    def _make_result(text_so_far: str = "") -> LLMResult:
        return LLMResult(
            text=text_so_far,
            emotion=emotion,
            face_state=face_state,
            provider=self.provider,
            model=self.model,
            latency_ms=int((perf_counter() - started) * 1000),
            finish_reason="stop",
            raw=None,
        )

    for chunk in response:
        try:
            delta = chunk.choices[0].delta.content or ""
        except Exception:
            delta = ""
        if not delta:
            continue
        if tags_done:
            yield delta, _make_result(delta)
            continue
        buffer += delta
        m = tag_pattern.match(buffer)
        if m:
            emotion = (m.group(1) or "neutral").lower()
            face_state = (m.group(2) or "SPEAKING").upper()
            tags_done = True
            tail = buffer[m.end():]
            if tail:
                yield tail, _make_result(tail)
            continue
        # If buffer is long enough yet no tags, fall back: treat all as text
        if len(buffer) > 60:
            tags_done = True
            yield buffer, _make_result(buffer)

    # Stream ended; if tags never closed but we had buffered content, flush
    if not tags_done and buffer:
        yield buffer, _make_result(buffer)


# Attach as method
SiliconFlowLLMProvider.stream_chat = stream_chat  # type: ignore[attr-defined]


def _parse_structured_reply(content: str) -> dict[str, str | None]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        text = str(parsed.get("assistant_text") or parsed.get("text") or "").strip()
        if text:
            return {
                "assistant_text": text,
                "emotion": _clean_optional(parsed.get("emotion")),
                "face_state": _clean_optional(parsed.get("face_state")),
            }
    return {
        "assistant_text": content,
        "emotion": "neutral",
        "face_state": "SPEAKING",
    }


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
