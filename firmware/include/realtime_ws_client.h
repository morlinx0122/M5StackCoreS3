#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <WebSocketsClient.h>
#include <functional>

class RealtimeWsClient {
 public:
  using StateCallback = std::function<void(const String&, const String&)>;
  using AudioChunkCallback = std::function<void(const String&, int, const String&, const String&, bool)>;
  using WakeDetectedCallback = std::function<void(const String& sessionId, const String& matched)>;

  void begin(const char* deviceId);
  void loop();
  bool isConnected() const;
  void sendHello();
  String startAudio(const char* mode = "session");
  void sendAudioFrame(const int16_t* samples, size_t sampleCount);
  void endAudio(const String& sessionId);
  void sendPlaybackDone(const String& sessionId, int chunkIndex, bool ok, unsigned long durationMs);

  void onState(StateCallback callback);
  void onAudioChunk(AudioChunkCallback callback);
  void onWakeDetected(WakeDetectedCallback callback);

 private:
  WebSocketsClient ws_;
  String deviceId_;
  String activeSessionId_;
  bool connected_ = false;
  StateCallback stateCallback_;
  AudioChunkCallback audioChunkCallback_;
  WakeDetectedCallback wakeDetectedCallback_;

  void handleEvent(WStype_t type, uint8_t* payload, size_t length);
  void handleText(const char* text);
  void sendJson(JsonDocument& doc);
  String newSessionId() const;
};
