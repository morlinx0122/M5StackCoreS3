from __future__ import annotations

from app.services.llm_router import get_llm_router


class StreamingLLMService:
    def stream_reply(self, user_text: str, device_id: str):
        """Yield (token, LLMResult) tuples in true streaming fashion when supported.

        Falls back to one-shot chat() when the underlying provider has no stream_chat.
        """
        router = get_llm_router()
        primary = getattr(router, "primary", None)
        stream_fn = getattr(primary, "stream_chat", None)
        if callable(stream_fn):
            try:
                yielded_any = False
                for token, result in stream_fn(
                    user_text=user_text,
                    scenario="deskbot_voice_short_reply",
                    device_id=device_id,
                ):
                    if token:
                        yielded_any = True
                        yield token, result
                if yielded_any:
                    return
            except Exception as exc:
                print(f"streaming LLM failed, falling back: {exc}", flush=True)

        # Fallback: blocking chat with fake-stream chunks
        result = router.chat(
            user_text=user_text,
            scenario="deskbot_voice_short_reply",
            device_id=device_id,
        )
        text = result.text.strip()
        for index in range(0, len(text), 8):
            yield text[index : index + 8], result
