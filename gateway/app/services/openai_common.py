import os

from openai import OpenAI


def openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "sk-your-api-key":
        raise RuntimeError("OPENAI_API_KEY is required when using OpenAI providers.")
    return OpenAI(api_key=api_key)
