#include "realtime_ws_client.h"

#include "config.h"

void RealtimeWsClient::begin(const char* deviceId) {
  deviceId_ = deviceId;
  String path = String("/ws/device/") + deviceId_;
  ws_.begin(GATEWAY_WS_HOST, GATEWAY_WS_PORT, path.c_str());
  ws_.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
    handleEvent(type, payload, length);
  });
  ws_.setReconnectInterval(3000);
  // Tolerate slower pong responses (e.g. while gateway is generating TTS) and
  // require more consecutive misses before declaring the link dead.
  ws_.enableHeartbeat(20000, 8000, 4);
}

void RealtimeWsClient::loop() {
  ws_.loop();
}

bool RealtimeWsClient::isConnected() const {
  return connected_;
}

void RealtimeWsClient::sendHello() {
  JsonDocument doc;
  doc["type"] = "device_hello";
  doc["device_id"] = deviceId_;
  doc["firmware_version"] = FIRMWARE_VERSION;
  JsonObject audio = doc["audio"].to<JsonObject>();
  audio["sample_rate"] = AUDIO_SAMPLE_RATE;
  audio["channels"] = 1;
  audio["format"] = "pcm_s16le";
  audio["frame_ms"] = AUDIO_FRAME_SAMPLES * 1000 / AUDIO_SAMPLE_RATE;
  sendJson(doc);
}

String RealtimeWsClient::startAudio(const char* mode) {
  activeSessionId_ = newSessionId();
  JsonDocument doc;
  doc["type"] = "audio_start";
  doc["session_id"] = activeSessionId_;
  doc["sample_rate"] = AUDIO_SAMPLE_RATE;
  doc["channels"] = 1;
  doc["format"] = "pcm_s16le";
  doc["mode"] = mode != nullptr && *mode ? mode : "session";
  sendJson(doc);
  return activeSessionId_;
}

void RealtimeWsClient::sendAudioFrame(const int16_t* samples, size_t sampleCount) {
  if (!connected_ || samples == nullptr || sampleCount == 0) {
    return;
  }
  ws_.sendBIN(reinterpret_cast<const uint8_t*>(samples), sampleCount * sizeof(int16_t));
}

void RealtimeWsClient::endAudio(const String& sessionId) {
  JsonDocument doc;
  doc["type"] = "audio_end";
  doc["session_id"] = sessionId;
  sendJson(doc);
}

void RealtimeWsClient::sendPlaybackDone(const String& sessionId, int chunkIndex, bool ok, unsigned long durationMs) {
  JsonDocument doc;
  doc["type"] = "playback_done";
  doc["session_id"] = sessionId;
  doc["chunk_index"] = chunkIndex;
  doc["status"] = ok ? "success" : "failed";
  doc["duration_ms"] = durationMs;
  sendJson(doc);
}

void RealtimeWsClient::onState(StateCallback callback) {
  stateCallback_ = callback;
}

void RealtimeWsClient::onAudioChunk(AudioChunkCallback callback) {
  audioChunkCallback_ = callback;
}

void RealtimeWsClient::onWakeDetected(WakeDetectedCallback callback) {
  wakeDetectedCallback_ = callback;
}

void RealtimeWsClient::handleEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      connected_ = true;
      Serial.println("Realtime WS connected");
      sendHello();
      break;
    case WStype_DISCONNECTED:
      connected_ = false;
      Serial.println("Realtime WS disconnected");
      break;
    case WStype_TEXT:
      handleText(reinterpret_cast<const char*>(payload));
      break;
    case WStype_BIN:
      Serial.printf("Unexpected realtime binary frame: %u bytes\n", static_cast<unsigned>(length));
      break;
    default:
      break;
  }
}

void RealtimeWsClient::handleText(const char* text) {
  Serial.printf("[WS<-] %s\n", text);
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, text);
  if (error) {
    Serial.printf("Realtime WS JSON parse failed: %s\n", error.c_str());
    return;
  }
  const char* type = doc["type"] | "";
  if (strcmp(type, "robot_state") == 0) {
    if (stateCallback_) {
      stateCallback_(doc["state"] | "", doc["face_state"] | "");
    }
  } else if (strcmp(type, "stt_partial") == 0) {
    if (stateCallback_) {
      stateCallback_("STT_PARTIAL", "LISTENING");
    }
  } else if (strcmp(type, "play_audio_chunk") == 0) {
    activeSessionId_ = String(doc["session_id"] | activeSessionId_.c_str());
    if (audioChunkCallback_) {
      audioChunkCallback_(
        activeSessionId_,
        doc["chunk_index"] | 0,
        doc["audio_url"] | "",
        doc["text"] | "",
        doc["is_final"] | false
      );
    }
  } else if (strcmp(type, "wake_detected") == 0) {
    String sid = String(doc["session_id"] | activeSessionId_.c_str());
    String matched = String(doc["matched"] | "");
    Serial.printf("[WAKE] device received wake_detected sid=%s matched=%s cb=%d\n",
                  sid.c_str(), matched.c_str(), wakeDetectedCallback_ ? 1 : 0);
    if (wakeDetectedCallback_) {
      wakeDetectedCallback_(sid, matched);
    }
  } else if (strcmp(type, "reply_end") == 0) {
    // Gateway flags end of TTS reply via reply_end (chunks themselves carry
    // is_final=false). Map it to an IDLE state so the device returns to
    // WAKE_LISTENING after speaking finishes.
    if (stateCallback_) {
      stateCallback_("IDLE", "IDLE");
    }
  }
}

void RealtimeWsClient::sendJson(JsonDocument& doc) {
  if (!connected_) {
    return;
  }
  String body;
  serializeJson(doc, body);
  ws_.sendTXT(body);
}

String RealtimeWsClient::newSessionId() const {
  return String("sess_") + String(millis(), HEX);
}
