#include "app_controller.h"

#include <ArduinoJson.h>
#include <M5Unified.h>
#include "config.h"
#include "wake_detector_factory.h"

AppController::AppController() : deviceClient_(GATEWAY_HOST) {}

void AppController::begin() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);
  delay(200);

  face_.begin();
  if (!audioEngine_.begin()) {
    Serial.println("AudioEngine init failed");
  }
  mic_.begin(&audioEngine_);
  wakeDetector_ = createWakeDetector();
  if (wakeDetector_ == nullptr || !wakeDetector_->begin()) {
    Serial.println("WakeDetector init failed, falling back to fake");
    wakeDetector_ = createFallbackWakeDetector();
    if (wakeDetector_ != nullptr) {
      wakeDetector_->begin();
    }
  }
  if (wakeDetector_ != nullptr) {
    Serial.printf("WakeDetector active: %s\n", wakeDetector_->name());
  }
  speaker_.begin();
  // Pump WS during blocking download/playback so server-side keepalive doesn't
  // disconnect us mid-TTS (which would drop reply_end and freeze the UI).
  speaker_.setPump([this]() { realtimeWs_.loop(); });
  configureRealtimeCallbacks();
  setState(RobotState::WIFI_CONNECTING);
  wifi_.begin();
}

void AppController::loop() {
  M5.update();
  wifi_.loop();
  // Skip the no-op audio prefetch when we're actively streaming for wake_watch,
  // otherwise readSamples competes with handleWakeWatch and halves the rate.
  if ((state_ == RobotState::IDLE || state_ == RobotState::WAKE_LISTENING) && !wakeWatchActive_) {
    audioEngine_.loop();
  }
  handleConnection();
  if (wifi_.isConnected() && registered_) {
    realtimeWs_.loop();
  }
  handleTouch();
  handleTimers();
  handleWakeWord();
  // Process deferred cloud wake BEFORE handleWakeWatch() — otherwise
  // handleWakeWatch sees wakeWatchActive_=false and immediately restarts
  // the streaming capture, stealing M5.Mic from runAudioChat().
  if (pendingCloudWakeChat_) {
    pendingCloudWakeChat_ = false;
    setState(RobotState::WAKE_DETECTED);
    face_.update(state_);
    runAudioChat();
  }
  handleWakeWatch();
  face_.update(state_);
}

void AppController::setState(RobotState state) {
  if (state_ == state) {
    return;
  }

  state_ = state;
  simulatedStateStartedMs_ = millis();
  Serial.printf("State -> %s\n", robotStateToString(state_));
  deviceClient_.sendStatus(state_);
}

void AppController::handleConnection() {
  if (!wifi_.isConnected()) {
    registered_ = false;
    if (state_ != RobotState::WIFI_CONNECTING) {
      setState(RobotState::WIFI_CONNECTING);
    }
    return;
  }

  if (!registered_) {
    setState(RobotState::REGISTERING);
    if (deviceClient_.registerDevice(wifi_.localIp())) {
      registered_ = true;
      realtimeWs_.begin(DEVICE_ID);
      setState(RobotState::WAKE_LISTENING);
    }
  }
}

void AppController::handleTouch() {
  TouchEvent event = touch_.update();
  if (event == TouchEvent::NONE) {
    return;
  }

  if (state_ == RobotState::SLEEPING) {
    setState(RobotState::WAKE_LISTENING);
    return;
  }

  if (event == TouchEvent::DOUBLE_TAP) {
    setState(RobotState::WAKE_LISTENING);
    return;
  }

  if (event == TouchEvent::SINGLE_TAP && (state_ == RobotState::IDLE || state_ == RobotState::WAKE_LISTENING)) {
    Serial.println("Fake wake triggered by single tap");
    if (wakeDetector_ != nullptr) {
      wakeDetector_->trigger();
    }
  }
}

void AppController::handleWakeWord() {
  if (!wifi_.isConnected() || !registered_) {
    return;
  }

  if (state_ == RobotState::IDLE) {
    setState(RobotState::WAKE_LISTENING);
    return;
  }

  if (state_ != RobotState::WAKE_LISTENING) {
    return;
  }

  if (wakeDetector_ == nullptr) {
    return;
  }

  int16_t samples[AUDIO_FRAME_SAMPLES];
  size_t count = audioEngine_.readLatestFrame(samples, AUDIO_FRAME_SAMPLES);
  WakeResult result = wakeDetector_->process(samples, count);
  if (result.type == WakeResultType::MATCHED) {
    Serial.printf("Wake detected: confidence=%.2f\n", result.confidence);
    setState(RobotState::WAKE_DETECTED);
    face_.update(state_);
    runAudioChat();
  }
}

bool AppController::containsWakeWord(const String& text) const {
  String normalized = text;
  normalized.replace(" ", "");
  normalized.replace("\n", "");
  normalized.replace("\r", "");
  normalized.replace("，", "");
  normalized.replace(",", "");
  normalized.replace("。", "");
  normalized.replace(".", "");
  normalized.replace("！", "");
  normalized.replace("!", "");
  normalized.replace("？", "");
  normalized.replace("?", "");

  String words = WAKE_WORDS;
  int start = 0;
  while (start < words.length()) {
    int comma = words.indexOf(',', start);
    String word = comma >= 0 ? words.substring(start, comma) : words.substring(start);
    word.trim();
    if (word.length() > 0 && normalized.indexOf(word) >= 0) {
      return true;
    }
    if (comma < 0) {
      break;
    }
    start = comma + 1;
  }
  return false;
}

void AppController::handleTimers() {
  if (!wifi_.isConnected() || !registered_) {
    return;
  }

  unsigned long now = millis();
  if (now - lastHealthCheckMs_ >= HEALTH_CHECK_INTERVAL_MS) {
    lastHealthCheckMs_ = now;
    if (!deviceClient_.healthCheck()) {
      setState(RobotState::ERROR_STATE);
    }
  }

  if (now - lastHeartbeatMs_ >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatMs_ = now;
    deviceClient_.sendHeartbeat(state_);
  }

  if ((state_ == RobotState::THINKING || state_ == RobotState::WAITING_REPLY) &&
      now - simulatedStateStartedMs_ >= THINKING_TIMEOUT_MS) {
    Serial.println("Waiting for reply timed out, returning to wake listening");
    setState(RobotState::WAKE_LISTENING);
  }

  unsigned long commandPollIntervalMs =
    state_ == RobotState::WAITING_REPLY ? COMMAND_POLL_WAITING_REPLY_MS : COMMAND_POLL_INTERVAL_MS;
  if (state_ == RobotState::SPEAKING) {
    commandPollIntervalMs = COMMAND_POLL_INTERVAL_MS * 4;
  }
  // While actively listening for cloud wake word, skip frequent command polls
  // (each HTTP GET takes 50-200ms which would block mic capture)
  if (state_ == RobotState::WAKE_LISTENING) {
    commandPollIntervalMs = COMMAND_POLL_INTERVAL_MS * 8;
  }

  if (now - lastCommandPollMs_ >= commandPollIntervalMs) {
    lastCommandPollMs_ = now;
    String commandResponse;
    if (deviceClient_.pollCommands(&commandResponse)) {
      JsonDocument doc;
      DeserializationError error = deserializeJson(doc, commandResponse);
      if (error) {
        Serial.printf("Command JSON parse failed: %s\n", error.c_str());
        return;
      }

      JsonArray commands = doc["data"]["commands"].as<JsonArray>();
      for (JsonObject command : commands) {
        String commandId;
        const char* cmdId = command["cmd_id"];
        if (cmdId != nullptr && strlen(cmdId) > 0) {
          commandId = cmdId;
        } else {
          int numericId = command["id"] | 0;
          if (numericId > 0) {
            commandId = String(numericId);
          }
        }

        const char* type = command["type"];
        if (type == nullptr) {
          deviceClient_.ackCommand(commandId, false, 0, "INVALID_COMMAND", "missing command type");
          continue;
        }

        if (strcmp(type, "play_audio") == 0) {
          const char* audioUrl = command["payload"]["url"];
          if (audioUrl == nullptr || strlen(audioUrl) == 0) {
            audioUrl = command["payload"]["audio_url"];
          }
          if (audioUrl != nullptr && strlen(audioUrl) > 0) {
            setState(RobotState::SPEAKING);
            face_.update(state_);
            audioEngine_.end();
            unsigned long playStartedMs = millis();
            bool played = speaker_.downloadAndPlay(audioUrl);
            unsigned long playedMs = millis() - playStartedMs;
            audioEngine_.begin();
            setState(RobotState::ACKING);
            face_.update(state_);
            deviceClient_.ackCommand(
              commandId,
              played,
              playedMs,
              played ? nullptr : "AUDIO_PLAY_FAILED",
              played ? nullptr : "speaker playback failed"
            );
            setState(RobotState::WAKE_LISTENING);
          } else {
            deviceClient_.ackCommand(commandId, false, 0, "INVALID_COMMAND", "missing audio url");
          }
        } else if (strcmp(type, "set_face") == 0) {
          const char* faceState = command["payload"]["state"];
          if (faceState != nullptr && strcmp(faceState, "THINKING") == 0) {
            setState(RobotState::WAITING_REPLY);
          } else if (faceState != nullptr && strcmp(faceState, "IDLE") == 0) {
            setState(RobotState::WAKE_LISTENING);
          }
          deviceClient_.ackCommand(commandId, true, 0);
        } else {
          deviceClient_.ackCommand(commandId, false, 0, "UNKNOWN_COMMAND", type);
        }
      }
    }
  }
}

void AppController::runAudioChat() {
  if (realtimeWs_.isConnected() && runRealtimeVoiceSession()) {
    return;
  }

  setState(RobotState::RECORDING);
  face_.update(state_);

  bool recorded = mic_.recordVad();
  if (!recorded) {
    Serial.println("No speech detected");
    setState(RobotState::WAKE_LISTENING);
    return;
  }

  submitRecordedAudioChat();
}

bool AppController::runRealtimeVoiceSession() {
  if (!audioEngine_.isReady()) {
    return false;
  }

  setState(RobotState::LISTENING_STREAM);
  face_.update(state_);
  realtimeSessionId_ = realtimeWs_.startAudio();

  constexpr size_t chunkSamples = AUDIO_FRAME_SAMPLES;
  constexpr size_t calibrationChunks = VAD_CALIBRATION_MS * AUDIO_SAMPLE_RATE / 1000 / chunkSamples;
  constexpr size_t minChunks = VAD_MIN_RECORD_MS * AUDIO_SAMPLE_RATE / 1000 / chunkSamples;
  constexpr size_t maxChunks = VAD_MAX_RECORD_MS * AUDIO_SAMPLE_RATE / 1000 / chunkSamples;
  constexpr size_t silenceEndChunks = VAD_SILENCE_END_MS * AUDIO_SAMPLE_RATE / 1000 / chunkSamples;
  constexpr size_t waitTimeoutChunks = VAD_WAIT_TIMEOUT_MS * AUDIO_SAMPLE_RATE / 1000 / chunkSamples;

  // C1: drain ~250ms of mic audio first so the trailing "大雷大雷" syllable
  // (and the prompt tone above) doesn't feed VAD/STT as user speech.
  {
    int16_t drain[chunkSamples];
      size_t drainChunks = 150 * AUDIO_SAMPLE_RATE / 1000 / chunkSamples;
    for (size_t i = 0; i < drainChunks; ++i) {
      audioEngine_.readSamples(drain, chunkSamples);
      realtimeWs_.loop();
    }
  }

  int16_t samples[chunkSamples];
  size_t chunksRead = 0;
  size_t recordedChunks = 0;
  size_t voicedChunks = 0;
  size_t silenceChunks = 0;
  uint32_t noiseTotal = 0;
  uint32_t threshold = VAD_MIN_THRESHOLD;
  bool speechStarted = false;

  Serial.println("Realtime streaming audio with local VAD...");
  while (recordedChunks < maxChunks) {
    M5.update();
    realtimeWs_.loop();
    if (audioEngine_.readSamples(samples, chunkSamples) != chunkSamples) {
      Serial.println("Realtime audio read failed");
      break;
    }
    chunksRead++;
    uint64_t total = 0;
    for (size_t i = 0; i < chunkSamples; ++i) {
      int32_t sample = samples[i];
      total += sample < 0 ? -sample : sample;
    }
    uint32_t level = static_cast<uint32_t>(total / chunkSamples);
    if (!speechStarted && chunksRead <= calibrationChunks) {
      noiseTotal += level;
      uint32_t noiseLevel = noiseTotal / chunksRead;
      uint32_t dynamicThreshold = noiseLevel * VAD_THRESHOLD_MULTIPLIER + VAD_THRESHOLD_OFFSET;
      threshold = dynamicThreshold > VAD_MIN_THRESHOLD ? dynamicThreshold : VAD_MIN_THRESHOLD;
      continue;
    }

    bool voiced = level >= threshold;
    if (!speechStarted) {
      if (voiced) {
        voicedChunks++;
        if (voicedChunks >= 1) {
          speechStarted = true;
          Serial.printf("Realtime speech start level=%u threshold=%u\n", level, threshold);
        }
      } else if (chunksRead > waitTimeoutChunks) {
        Serial.println("Realtime VAD timeout waiting for speech");
        realtimeWs_.endAudio(realtimeSessionId_);
        setState(RobotState::WAKE_LISTENING);
        return false;
      }
      continue;
    }

    realtimeWs_.sendAudioFrame(samples, chunkSamples);
    recordedChunks++;
    if (voiced) {
      silenceChunks = 0;
    } else {
      silenceChunks++;
      if (recordedChunks >= minChunks && silenceChunks >= silenceEndChunks) {
        Serial.println("Realtime speech end");
        break;
      }
    }
  }

  realtimeWs_.endAudio(realtimeSessionId_);
  setState(RobotState::THINKING);
  return true;
}

void AppController::configureRealtimeCallbacks() {
  realtimeWs_.onState([this](const String& state, const String&) {
    applyRealtimeState(state);
  });
  realtimeWs_.onAudioChunk([this](const String& sessionId, int chunkIndex, const String& audioUrl, const String& text, bool isFinal) {
    playRealtimeAudioChunk(sessionId, chunkIndex, audioUrl, text, isFinal);
  });
  realtimeWs_.onWakeDetected([this](const String& sessionId, const String& matched) {
    onWakeDetectedFromCloud(sessionId, matched);
  });
}

void AppController::handleWakeWatch() {
#if CLOUD_WAKE_WATCH_ENABLED
  if (!wifi_.isConnected() || !registered_ || !realtimeWs_.isConnected()) {
    if (wakeWatchActive_) {
      wakeWatchActive_ = false;
    }
    return;
  }
  if (state_ != RobotState::WAKE_LISTENING) {
    if (wakeWatchActive_) {
      // Leaving WAKE_LISTENING: close wake-watch session cleanly
      realtimeWs_.endAudio(wakeWatchSessionId_);
      wakeWatchActive_ = false;
      wakeWatchEndedAtMs_ = millis();
      audioEngine_.stopContinuousCapture();
    }
    return;
  }
  if (!audioEngine_.isReady()) {
    return;
  }
  if (!wakeWatchActive_) {
    if (millis() - wakeWatchEndedAtMs_ < CLOUD_WAKE_RESTART_MIN_MS) {
      return;
    }
    wakeWatchSessionId_ = realtimeWs_.startAudio("wake_watch");
    wakeWatchActive_ = true;
    // Spin up dedicated FreeRTOS capture task pinned to core 0 so audio is
    // sampled continuously regardless of main-loop blocking work (face/HTTP/WS).
    audioEngine_.startContinuousCapture();
    Serial.printf("Cloud wake-watch started session=%s\n", wakeWatchSessionId_.c_str());
    return;
  }
  // Drain whatever the capture task has buffered (up to 200ms worth).
  static constexpr size_t WAKE_CHUNK_SAMPLES = 3200; // 200 ms @ 16 kHz
  static int16_t wakeBuf[WAKE_CHUNK_SAMPLES];
  size_t count = audioEngine_.popContinuous(wakeBuf, WAKE_CHUNK_SAMPLES);
  if (count > 0) {
    realtimeWs_.sendAudioFrame(wakeBuf, count);
  }
#endif
}

void AppController::onWakeDetectedFromCloud(const String& sessionId, const String& matched) {
  Serial.printf("Cloud wake detected: matched='%s' session=%s\n", matched.c_str(), sessionId.c_str());
  // Close the wake-watch session and flag the main loop to run the chat.
  // We MUST NOT call runAudioChat() here because this runs inside the WS task
  // context — heavy work / nested WS calls will starve the WS handler and
  // trigger the watchdog, causing a reset.
  if (wakeWatchActive_) {
    realtimeWs_.endAudio(wakeWatchSessionId_);
    wakeWatchActive_ = false;
    wakeWatchEndedAtMs_ = millis();
    audioEngine_.stopContinuousCapture();
  }
  pendingCloudWakeChat_ = true;
}

void AppController::playRealtimeAudioChunk(
  const String& sessionId,
  int chunkIndex,
  const String& audioUrl,
  const String& text,
  bool isFinal
) {
  realtimeSessionId_ = sessionId;
  Serial.printf("Realtime audio chunk %d final=%d text=%s\n", chunkIndex, isFinal, text.c_str());
  setState(RobotState::SPEAKING_STREAM);
  audioEngine_.end();
  unsigned long startedMs = millis();
  bool ok = speaker_.downloadAndPlay(audioUrl);
  unsigned long playedMs = millis() - startedMs;
  realtimeWs_.sendPlaybackDone(sessionId, chunkIndex, ok, playedMs);
  audioEngine_.begin();
  if (isFinal) {
    setState(RobotState::WAKE_LISTENING);
  }
}

void AppController::applyRealtimeState(const String& state) {
  if (state == "LISTENING_STREAM") {
    setState(RobotState::LISTENING_STREAM);
  } else if (state == "STT_PARTIAL") {
    setState(RobotState::STT_PARTIAL);
  } else if (state == "THINKING") {
    setState(RobotState::THINKING);
  } else if (state == "SPEAKING_STREAM") {
    setState(RobotState::SPEAKING_STREAM);
  } else if (state == "INTERRUPTED") {
    setState(RobotState::INTERRUPTED);
  } else if (state == "IDLE") {
    setState(RobotState::WAKE_LISTENING);
  }
}

void AppController::submitRecordedAudioChat() {
  setState(RobotState::UPLOADING);
  face_.update(state_);

  String response;
  if (!deviceClient_.uploadAudioChat(mic_.wavData(), mic_.wavSize(), state_, &response)) {
    Serial.println("Audio chat upload failed");
    setState(RobotState::ERROR_STATE);
    return;
  }

  Serial.printf("Audio chat response: %s\n", response.c_str());
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, response);
  if (!error) {
    const char* status = doc["data"]["status"];
    if (status != nullptr && strcmp(status, "accepted") == 0) {
      setState(RobotState::WAITING_REPLY);
      return;
    }

    const char* audioUrl = doc["data"]["audio_url"];
    if (audioUrl != nullptr && strlen(audioUrl) > 0) {
      setState(RobotState::SPEAKING);
      audioEngine_.end();
      speaker_.downloadAndPlay(audioUrl);
      audioEngine_.begin();
    } else {
      delay(1200);
    }
  } else {
    Serial.printf("Audio chat JSON parse failed: %s\n", error.c_str());
    delay(1200);
  }

  setState(RobotState::WAKE_LISTENING);
}
