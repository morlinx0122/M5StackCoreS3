import os
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from zoneinfo import ZoneInfo

import httpx
from openai import OpenAI

from app.services.openai_common import openai_client


def current_context() -> str:
    timezone_name = os.getenv("LOCAL_TIMEZONE", "Asia/Shanghai")
    now = datetime.now(ZoneInfo(timezone_name))
    return f"当前日期时间：{now:%Y-%m-%d %H:%M:%S}，时区：{timezone_name}。"


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    finish_reason: str = "stop"


class LLMService:
    provider = "base"
    model = "base"

    def chat(self, user_text: str, scenario: str = "deskbot") -> LLMResult:
        raise NotImplementedError


class MockLLMService(LLMService):
    provider = "mock"
    model = "mock-chat-v0"

    def chat(self, user_text: str, scenario: str = "deskbot") -> LLMResult:
        started = perf_counter()
        normalized_text = user_text.rstrip("。.!！?？ ")
        template = os.getenv(
            "MOCK_LLM_TEMPLATE",
            "我听到了：{user_text}。下一步接入真实大模型后，我会给你更自然的回答。",
        )
        text = template.format(user_text=normalized_text, scenario=scenario)
        return LLMResult(
            text=text,
            provider=self.provider,
            model=self.model,
            latency_ms=int((perf_counter() - started) * 1000),
        )


class OpenAILLMService(LLMService):
    provider = "openai"

    def __init__(self) -> None:
        self.client = openai_client()
        self.model = os.getenv("OPENAI_LLM_MODEL", "gpt-5.4-mini")
        self.instructions = os.getenv(
            "OPENAI_LLM_INSTRUCTIONS",
            "你是一个温和、简洁、可靠的桌面 AI 机器人助理。回答要自然，适合通过语音朗读。",
        )

    def chat(self, user_text: str, scenario: str = "deskbot") -> LLMResult:
        started = perf_counter()
        response = self.client.responses.create(
            model=self.model,
            instructions=self.instructions,
            input=f"场景：{scenario}\n用户：{user_text}",
        )
        text = getattr(response, "output_text", "") or self._extract_output_text(response)
        return LLMResult(
            text=text.strip(),
            provider=self.provider,
            model=self.model,
            latency_ms=int((perf_counter() - started) * 1000),
        )

    def _extract_output_text(self, response) -> str:
        parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    parts.append(text)
        return "\n".join(parts)


class OpenAICompatibleLLMService(LLMService):
    provider = "openai_compatible"

    def __init__(
        self,
        provider: str,
        api_key_env: str,
        base_url_env: str,
        model_env: str,
        default_base_url: str,
        default_model: str,
    ) -> None:
        api_key = os.getenv(api_key_env, "").strip()
        if not api_key and api_key_env == "MIMO_API_KEY":
            api_key = os.getenv("XIAOMI_API_KEY", "").strip()
        if not api_key:
            if api_key_env == "MIMO_API_KEY":
                raise RuntimeError("MIMO_API_KEY or XIAOMI_API_KEY is required when using mimo.")
            raise RuntimeError(f"{api_key_env} is required when using {provider}.")

        self.provider = provider
        self.model = os.getenv(model_env, default_model)
        self.client = OpenAI(
            api_key=api_key,
            base_url=os.getenv(base_url_env, default_base_url),
        )
        self.instructions = os.getenv(
            "LLM_SYSTEM_PROMPT",
            "你是一个温和、简洁、可靠的桌面 AI 机器人助理。回答要自然，适合通过语音朗读。",
        )
        self.web_search_enabled = os.getenv("MIMO_WEB_SEARCH_ENABLED", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def chat(self, user_text: str, scenario: str = "deskbot") -> LLMResult:
        started = perf_counter()
        request = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": f"{self.instructions}\n{current_context()}"},
                {"role": "user", "content": f"场景：{scenario}\n用户：{user_text}"},
            ],
        }
        if self.provider == "mimo" and self.web_search_enabled:
            request["tools"] = [
                {
                    "type": "web_search",
                    "max_keyword": int(os.getenv("MIMO_WEB_SEARCH_MAX_KEYWORD", "3")),
                    "force_search": os.getenv("MIMO_WEB_SEARCH_FORCE", "false").strip().lower()
                    in {"1", "true", "yes", "on"},
                    "limit": int(os.getenv("MIMO_WEB_SEARCH_LIMIT", "1")),
                },
            ]
            request["tool_choice"] = "auto"

        try:
            response = self.client.chat.completions.create(**request)
        except Exception as exc:
            if self.provider == "mimo" and self.web_search_enabled and "webSearchEnabled is false" in str(exc):
                print("MiMo web search plugin is disabled; retrying without web_search.", flush=True)
                request.pop("tools", None)
                request.pop("tool_choice", None)
                request["messages"].append(
                    {
                        "role": "system",
                        "content": (
                            "联网搜索插件当前未启用。遇到天气、新闻、股价、实时政策等需要联网的请求时，"
                            "不要编造具体实时结果，应简短说明暂时无法联网查询。"
                        ),
                    }
                )
                response = self.client.chat.completions.create(**request)
            else:
                raise
        message = response.choices[0].message
        return LLMResult(
            text=(message.content or "").strip(),
            provider=self.provider,
            model=self.model,
            latency_ms=int((perf_counter() - started) * 1000),
            finish_reason=response.choices[0].finish_reason or "stop",
        )


class QwenLLMService(OpenAICompatibleLLMService):
    def __init__(self) -> None:
        super().__init__(
            provider="qwen",
            api_key_env="QWEN_API_KEY",
            base_url_env="QWEN_BASE_URL",
            model_env="QWEN_LLM_MODEL",
            default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            default_model="qwen-plus",
        )


class DeepSeekLLMService(OpenAICompatibleLLMService):
    def __init__(self) -> None:
        super().__init__(
            provider="deepseek",
            api_key_env="DEEPSEEK_API_KEY",
            base_url_env="DEEPSEEK_BASE_URL",
            model_env="DEEPSEEK_LLM_MODEL",
            default_base_url="https://api.deepseek.com",
            default_model="deepseek-chat",
        )


class SiliconFlowLLMService(OpenAICompatibleLLMService):
    def __init__(self) -> None:
        super().__init__(
            provider="siliconflow",
            api_key_env="SILICONFLOW_API_KEY",
            base_url_env="SILICONFLOW_BASE_URL",
            model_env="SILICONFLOW_LLM_MODEL",
            default_base_url="https://api.siliconflow.cn/v1",
            default_model="stepfun-ai/Step-3.5-Flash",
        )


class MiMoLLMService(OpenAICompatibleLLMService):
    def __init__(self) -> None:
        super().__init__(
            provider="mimo",
            api_key_env="MIMO_API_KEY",
            base_url_env="MIMO_BASE_URL",
            model_env="MIMO_LLM_MODEL",
            default_base_url="https://api.xiaomimimo.com/v1",
            default_model="mimo-v2.5",
        )


class OllamaLLMService(LLMService):
    provider = "ollama"

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:7b")
        self.instructions = os.getenv(
            "LLM_SYSTEM_PROMPT",
            "你是一个温和、简洁、可靠的桌面 AI 机器人助理。回答要自然，适合通过语音朗读。",
        )

    def chat(self, user_text: str, scenario: str = "deskbot") -> LLMResult:
        started = perf_counter()
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": self.instructions},
                    {"role": "user", "content": f"场景：{scenario}\n用户：{user_text}"},
                ],
            },
            timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60")),
            trust_env=False,
        )
        response.raise_for_status()
        payload = response.json()
        text = (payload.get("message") or {}).get("content", "")
        return LLMResult(
            text=text.strip(),
            provider=self.provider,
            model=self.model,
            latency_ms=int((perf_counter() - started) * 1000),
        )


class FallbackLLMService(LLMService):
    provider = "fallback"

    def __init__(self, primary_provider: str, fallback_provider: str) -> None:
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider
        self.model = f"{primary_provider}->{fallback_provider}"

    def chat(self, user_text: str, scenario: str = "deskbot") -> LLMResult:
        try:
            return build_llm_service(self.primary_provider).chat(user_text=user_text, scenario=scenario)
        except Exception as exc:
            print(
                f"LLM provider failed primary={self.primary_provider} "
                f"fallback={self.fallback_provider} error={exc}",
                flush=True,
            )
            result = build_llm_service(self.fallback_provider).chat(user_text=user_text, scenario=scenario)
            return LLMResult(
                text=result.text,
                provider=f"{result.provider}_fallback",
                model=result.model,
                latency_ms=result.latency_ms,
                finish_reason=f"fallback:{self.primary_provider}",
            )


def build_llm_service(provider: str) -> LLMService:
    if provider == "mock":
        return MockLLMService()
    if provider == "qwen":
        return QwenLLMService()
    if provider == "deepseek":
        return DeepSeekLLMService()
    if provider == "siliconflow":
        return SiliconFlowLLMService()
    if provider == "mimo":
        return MiMoLLMService()
    if provider == "ollama":
        return OllamaLLMService()
    if provider == "openai":
        return OpenAILLMService()

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def get_llm_service() -> LLMService:
    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    fallback_provider = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()
    if fallback_provider and fallback_provider != provider:
        return FallbackLLMService(provider, fallback_provider)
    return build_llm_service(provider)


def run_chat(user_text: str, scenario: str = "deskbot") -> dict:
    result = get_llm_service().chat(user_text=user_text, scenario=scenario)
    return {
        "assistant_text": result.text,
        "llm": {
            "provider": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "finish_reason": result.finish_reason,
        },
    }
