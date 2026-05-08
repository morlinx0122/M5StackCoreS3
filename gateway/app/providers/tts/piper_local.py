from app.providers.tts.cached_audio_tts import CachedAudioTTSProvider


class PiperLocalTTSProvider(CachedAudioTTSProvider):
    provider = "piper_local"

