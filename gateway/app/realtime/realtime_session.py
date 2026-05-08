from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import WebSocket

from app.realtime.audio_frame_buffer import AudioFrameBuffer
from app.realtime.endpoint_detector import EndpointDetector
from app.realtime.realtime_trace import create_session, mark
from app.realtime.sentence_chunker import SentenceChunker
from app.realtime.streaming_llm_service import StreamingLLMService
from app.realtime.streaming_stt_service import StreamingSTTService, is_meaningful_stt
from app.realtime.tts_chunk_service import TTSChunkService
from app.realtime.wake_matcher import WakeMatcher
from app.services.fast_intent_router import route_fast_intent


class RealtimeVoiceSession:
    def __init__(self, websocket: WebSocket, device_id: str) -> None:
        self.websocket = websocket
        self.device_id = device_id
        self.session_id = f"sess_{uuid4().hex}"
        self.buffer = AudioFrameBuffer()
        self.stt = StreamingSTTService()
        self.vad = EndpointDetector()
        self.llm = StreamingLLMService()
        self.tts = TTSChunkService()
        self.chunk_index = 0
        self.started = perf_counter()
        # streaming partial throttling
        self._partial_interval_bytes = int(
            os.getenv("FUNASR_PARTIAL_INTERVAL_BYTES", str(16000 * 2 // 2))  # ~500ms
        )
        self._next_partial_at_bytes = self._partial_interval_bytes
        self._partial_inflight = False
        self._last_partial_text = ""
        self._cumulative_in_bytes: int = 0  # monotonically increasing across trims
        # mode: "session" (normal voice query) | "wake_watch" (cloud wake word listening)
        self.mode: str = "session"
        self.wake_matcher = WakeMatcher(cooldown_sec=1.5)
        # Sliding-window cap for wake_watch — short clips give SenseVoice better accuracy
        self._wake_window_bytes: int = 16000 * 2 * 3  # ~3 seconds
        # Wake-watch partial interval: ~1.5s so SenseVoice CPU load stays sane
        self._wake_partial_interval_bytes: int = int(16000 * 2 * 1.5)

    async def start(self) -> None:
        create_session(self.session_id, self.device_id)
        await self.send_json(
            {
                "type": "session_started",
                "session_id": self.session_id,
                "device_id": self.device_id,
            }
        )
        await self.send_robot_state("IDLE", "IDLE")

    async def handle_json(self, payload: dict) -> None:
        msg_type = payload.get("type")
        if msg_type == "device_hello":
            await self.send_json({"type": "device_ready", "session_id": self.session_id})
            return
        if msg_type == "audio_start":
            self.session_id = str(payload.get("session_id") or f"sess_{uuid4().hex}")
            self.buffer.clear()
            self.chunk_index = 0
            self.started = perf_counter()
            self._next_partial_at_bytes = self._partial_interval_bytes
            self._partial_inflight = False
            self._last_partial_text = ""
            self._cumulative_in_bytes = 0
            requested_mode = str(payload.get("mode") or "session").lower()
            self.mode = "wake_watch" if requested_mode == "wake_watch" else "session"
            create_session(self.session_id, self.device_id)
            if self.mode == "wake_watch":
                self.wake_matcher.reset_cooldown()
                print(f"[WAKE] {self.session_id} wake_watch started", flush=True)
                await self.send_robot_state("WAKE_LISTENING", "IDLE")
            else:
                await self.send_robot_state("LISTENING_STREAM", "LISTENING")
            return
        if msg_type == "audio_end":
            if self.mode == "wake_watch":
                # Device closed audio without wake word matched: just clear buffer, stay in wake_watch
                self.buffer.clear()
                self._next_partial_at_bytes = self._partial_interval_bytes
                self._cumulative_in_bytes = 0
                self._last_partial_text = ""
                return
            await self.finish_audio()
            return
        if msg_type == "playback_done":
            chunk_index = int(payload.get("chunk_index") or 0)
            mark(
                str(payload.get("session_id") or self.session_id),
                "completed",
                playback_end_at=True,
                total_latency_ms=int((perf_counter() - self.started) * 1000),
            )
            await self.send_json(
                {
                    "type": "playback_ack",
                    "session_id": str(payload.get("session_id") or self.session_id),
                    "chunk_index": chunk_index,
                }
            )
            return
        if msg_type == "interrupt":
            mark(self.session_id, "interrupted")
            await self.send_robot_state("INTERRUPTED", "IDLE")

    async def handle_audio_frame(self, frame: bytes) -> None:
        first = self.buffer.first_audio_at is None
        self.buffer.append(frame)
        self._cumulative_in_bytes += len(frame)
        if first:
            mark(self.session_id, first_audio_in_at=True)
            print(f"[WAKE] {self.session_id} first audio frame received bytes={len(frame)}", flush=True)
            self._first_audio_wall = perf_counter()
        # Periodic dump (every ~5s of cumulative input) for wake_watch debugging
        if self.mode == "wake_watch":
            dump_every = 16000 * 2 * 5
            if self._cumulative_in_bytes // dump_every > getattr(self, "_last_dump_marker", 0):
                self._last_dump_marker = self._cumulative_in_bytes // dump_every
                try:
                    self._dump_wav_snapshot()
                except Exception as exc:
                    print(f"[WAKE] dump error: {exc}", flush=True)
        # In wake_watch mode, keep only a sliding window so partial STT stays fast
        if self.mode == "wake_watch" and self.buffer.size_bytes > self._wake_window_bytes:
            self._trim_buffer_to(self._wake_window_bytes)
        await self._maybe_emit_partial()

    def _dump_wav_snapshot(self) -> None:
        import wave
        from pathlib import Path as _P
        out_dir = _P(".logs/wake_dumps")
        out_dir.mkdir(parents=True, exist_ok=True)
        idx = getattr(self, "_dump_idx", 0)
        self._dump_idx = idx + 1
        path = out_dir / f"{self.session_id}_{idx:03d}.wav"
        pcm = b"".join(self.buffer.frames)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm)
        rms = 0
        if pcm:
            import struct
            samples = struct.unpack(f"<{len(pcm)//2}h", pcm)
            sq = sum(s * s for s in samples) / len(samples)
            rms = int(sq ** 0.5)
        print(f"[WAKE] {self.session_id} dump #{idx} wrote {len(pcm)} bytes rms={rms} -> {path}", flush=True)
        # Log effective sample rate based on wall-clock vs cumulative bytes received
        elapsed = perf_counter() - getattr(self, "_first_audio_wall", perf_counter())
        if elapsed > 0:
            eff_rate = (self._cumulative_in_bytes / 2) / elapsed
            print(f"[WAKE] {self.session_id} effective_sample_rate={eff_rate:.1f}Hz (cumulative={self._cumulative_in_bytes}B over {elapsed:.2f}s)", flush=True)

    def _trim_buffer_to(self, max_bytes: int) -> None:
        """Drop oldest frames until buffer.size_bytes <= max_bytes (wake_watch only)."""
        frames = self.buffer.frames
        total = self.buffer.size_bytes
        idx = 0
        while total > max_bytes and idx < len(frames):
            total -= len(frames[idx])
            idx += 1
        if idx > 0:
            del frames[:idx]

    async def _maybe_emit_partial(self) -> None:
        # Use a longer interval in wake_watch mode (SenseVoice is heavier than streaming)
        interval = self._wake_partial_interval_bytes if self.mode == "wake_watch" else self._partial_interval_bytes
        if self._cumulative_in_bytes < self._next_partial_at_bytes or self._partial_inflight:
            return
        self._partial_inflight = True
        self._next_partial_at_bytes = self._cumulative_in_bytes + interval
        pcm_snapshot = b"".join(self.buffer.frames)
        try:
            if self.mode == "wake_watch":
                # Compute effective sample rate based on wall-clock (ESP32 mic captures < 16kHz reliably)
                elapsed = perf_counter() - getattr(self, "_first_audio_wall", perf_counter())
                effective_rate = self.buffer.sample_rate
                if elapsed > 1.0:
                    measured = (self._cumulative_in_bytes / 2) / elapsed
                    if 4000 <= measured <= 22000:
                        effective_rate = int(measured)
                # SenseVoice gives much better Chinese name accuracy on short clips
                payload = await asyncio.to_thread(
                    self.stt.sensevoice_from_pcm_bytes, pcm_snapshot, effective_rate, "zh"
                )
            else:
                payload = await asyncio.to_thread(
                    self.stt.partial_from_pcm_bytes, pcm_snapshot, self.buffer.sample_rate, False
                )
        except Exception as exc:  # defensive
            print(f"partial dispatch error: {exc}", flush=True)
            payload = None
        finally:
            self._partial_inflight = False
        if not payload:
            return
        text = str(payload.get("text") or "").strip()
        if self.mode == "wake_watch":
            # debug: log every partial in wake_watch (including empty) so we can see what model hears
            print(f"[WAKE] {self.session_id} partial_raw text='{text}' bytes={len(pcm_snapshot)}", flush=True)
        if not text or text == self._last_partial_text:
            return
        self._last_partial_text = text
        if self.mode == "wake_watch":
            print(f"[WAKE] {self.session_id} partial='{text}'", flush=True)
        mark(
            self.session_id,
            partial_text=text,
            stt_streaming_model=str(payload.get("model") or "paraformer-zh-streaming"),
        )
        # In wake_watch mode, do NOT push stt_partial to device: device's state machine
        # would transition out of WAKE_LISTENING which would close the wake-watch session.
        if self.mode != "wake_watch":
            await self.send_json({"type": "stt_partial", "session_id": self.session_id, "text": text})

        # Wake watch: check for wake word in partial transcript
        if self.mode == "wake_watch":
            matched = self.wake_matcher.match(text)
            if matched:
                print(f"[WAKE] {self.session_id} matched='{matched}' partial='{text}'", flush=True)
                # Switch to active session: reset buffer/state, transition state, notify device
                self.mode = "session"
                self.buffer.clear()
                self.chunk_index = 0
                self.started = perf_counter()
                self._next_partial_at_bytes = self._partial_interval_bytes
                self._partial_inflight = False
                self._last_partial_text = ""
                self._cumulative_in_bytes = 0
                mark(self.session_id, "wake_detected", wake_word=matched)
                await self.send_json(
                    {
                        "type": "wake_detected",
                        "session_id": self.session_id,
                        "matched": matched,
                        "partial": text,
                    }
                )
                await self.send_robot_state("LISTENING_STREAM", "LISTENING")

    async def finish_audio(self) -> None:
        t_speech_end = perf_counter()
        print(f"[TIMING] {self.session_id} speech_end (offset={int((t_speech_end-self.started)*1000)}ms)", flush=True)
        mark(self.session_id, "stt_finalizing", speech_end_at=True)
        await self.send_robot_state("THINKING", "THINKING")
        wav_path = self.buffer.to_wav_file(Path("app/static/audio/input"))

        # Optional VAD evidence (does not block flow on failure)
        t_vad_start = perf_counter()
        try:
            vad_result = await asyncio.to_thread(self.vad.detect, wav_path)
        except Exception as exc:
            print(f"VAD dispatch error: {exc}", flush=True)
            vad_result = None
        print(f"[TIMING] {self.session_id} vad_done (+{int((perf_counter()-t_vad_start)*1000)}ms)", flush=True)
        if vad_result is not None:
            mark(
                self.session_id,
                user_event="speech" if vad_result.speech_detected else "silence",
            )

        t_stt_start = perf_counter()
        stt_result = await asyncio.to_thread(self.stt.final_from_wav, wav_path)
        print(f"[TIMING] {self.session_id} stt_final (+{int((perf_counter()-t_stt_start)*1000)}ms) provider={stt_result.provider}", flush=True)
        final_text = (stt_result.text or "").strip()
        mark(
            self.session_id,
            "stt_final",
            final_text=final_text,
            user_emotion=stt_result.emotion,
            user_event=stt_result.event,
            stt_provider=stt_result.provider,
            stt_final_model=stt_result.model,
            stt_final_at=True,
        )
        await self.send_json(
            {
                "type": "stt_final",
                "session_id": self.session_id,
                "text": final_text,
                "language": stt_result.language or "zh",
                "emotion": stt_result.emotion or "neutral",
                "event": stt_result.event or "speech",
            }
        )

        if not is_meaningful_stt(final_text):
            mark(self.session_id, "no_speech")
            await self.send_robot_state("IDLE", "IDLE")
            await self.send_json({"type": "reply_end", "session_id": self.session_id})
            return

        fast_intent = route_fast_intent(final_text)
        if fast_intent is not None:
            await self.reply_fast_intent(fast_intent)
            return
        await self.reply_streaming_llm(final_text)

    async def reply_fast_intent(self, fast_intent) -> None:
        mark(
            self.session_id,
            "fast_intent",
            assistant_text=fast_intent.assistant_text,
            intent=fast_intent.intent,
            fast_intent_hit=1,
            llm_provider="fast_intent",
            llm_model=fast_intent.intent,
            fast_intent_done_at=True,
        )
        tts_result, audio_url, _ = self.next_tts_chunk(fast_intent.assistant_text, fast_intent.cached_audio_key)
        mark(
            self.session_id,
            "speaking",
            tts_provider=tts_result.provider,
            tts_model=tts_result.model,
            tts_voice=tts_result.voice,
            tts_first_audio_at=True,
            first_response_latency_ms=int((perf_counter() - self.started) * 1000),
        )
        await self.send_play_audio_chunk(audio_url, fast_intent.assistant_text, fast_intent.emotion, fast_intent.face_state, True)

    async def reply_streaming_llm(self, final_text: str) -> None:
        chunker = SentenceChunker(min_chars=8, max_chars=20)
        first_result = None
        full_text = ""
        t_llm_start = perf_counter()
        first_chunk_logged = False
        for token, llm_result in self.llm.stream_reply(final_text, self.device_id):
            if first_result is None:
                first_result = llm_result
                print(f"[TIMING] {self.session_id} llm_first_token (+{int((perf_counter()-t_llm_start)*1000)}ms) model={llm_result.model}", flush=True)
                mark(
                    self.session_id,
                    "llm_streaming",
                    llm_provider=llm_result.provider,
                    llm_model=llm_result.model,
                    llm_first_token_at=True,
                )
            full_text += token
            for chunk in chunker.push(token):
                if not first_chunk_logged:
                    print(f"[TIMING] {self.session_id} llm_first_sentence (+{int((perf_counter()-t_llm_start)*1000)}ms) text='{chunk[:30]}'", flush=True)
                    first_chunk_logged = True
                await self.speak_text_chunk(chunk, llm_result)
        tail = chunker.flush()
        if tail and first_result is not None:
            await self.speak_text_chunk(tail, first_result)
        if first_result is not None:
            mark(self.session_id, assistant_text=full_text)
        await self.send_json({"type": "reply_end", "session_id": self.session_id})

    async def speak_text_chunk(self, text: str, llm_result) -> None:
        t_tts_start = perf_counter()
        tts_result, audio_url, _ = self.next_tts_chunk(text)
        print(f"[TIMING] {self.session_id} tts_chunk_{self.chunk_index} (+{int((perf_counter()-t_tts_start)*1000)}ms) provider={tts_result.provider} text='{text[:30]}'", flush=True)
        mark(
            self.session_id,
            "speaking",
            tts_provider=tts_result.provider,
            tts_model=tts_result.model,
            tts_voice=tts_result.voice,
            tts_first_audio_at=True,
            llm_first_sentence_at=True,
            first_response_latency_ms=int((perf_counter() - self.started) * 1000),
        )
        await self.send_play_audio_chunk(audio_url, text, llm_result.emotion or "happy", llm_result.face_state or "SPEAKING", False)

    def next_tts_chunk(self, text: str, cache_key: str | None = None):
        self.chunk_index += 1
        return self.tts.chunk_for_text(self.session_id, self.chunk_index, text, cache_key)

    async def send_play_audio_chunk(
        self,
        audio_url: str,
        text: str,
        emotion: str,
        face_state: str,
        is_final: bool,
    ) -> None:
        await self.send_json(
            {
                "type": "play_audio_chunk",
                "session_id": self.session_id,
                "chunk_index": self.chunk_index,
                "audio_url": audio_url,
                "text": text,
                "emotion": emotion,
                "face_state": face_state,
                "is_final": is_final,
            }
        )

    async def send_robot_state(self, state: str, face_state: str) -> None:
        await self.send_json({"type": "robot_state", "state": state, "face_state": face_state})

    async def send_json(self, payload: dict) -> None:
        await self.websocket.send_text(json.dumps(payload, ensure_ascii=False))
