#include "speaker_player.h"

#include <HTTPClient.h>
#include <M5Unified.h>
#include <WiFi.h>
#include "config.h"

namespace {
constexpr int kMinWavBytes = 44;
constexpr int kMaxWavBytes = 2 * 1024 * 1024;
constexpr unsigned long kPlaybackTimeoutMs = 120000;
constexpr uint8_t kSpeakerVolume = 230;
}

bool SpeakerPlayer::begin() {
  M5.Speaker.setVolume(kSpeakerVolume);
  return true;
}

bool SpeakerPlayer::downloadAndPlay(const String& audioUrl) {
  if (WiFi.status() != WL_CONNECTED || audioUrl.isEmpty()) {
    return false;
  }

  HTTPClient http;
  http.setTimeout(15000);
  String url = absoluteUrl(audioUrl);
  http.begin(url);
  if (pump_) pump_();

  int code = http.GET();
  if (pump_) pump_();
  if (code < 200 || code >= 300) {
    Serial.printf("GET audio %s -> %d\n", url.c_str(), code);
    http.end();
    return false;
  }

  int size = http.getSize();
  if (size <= kMinWavBytes || size > kMaxWavBytes) {
    Serial.printf("Unexpected audio size: %d\n", size);
    http.end();
    return false;
  }

  uint8_t* buffer = static_cast<uint8_t*>(ps_malloc(size));
  if (buffer == nullptr) {
    Serial.println("Audio playback buffer allocation failed");
    http.end();
    return false;
  }

  WiFiClient* stream = http.getStreamPtr();
  size_t offset = 0;
  unsigned long lastReadMs = millis();
  while (offset < static_cast<size_t>(size)) {
    size_t available = stream->available();
    if (available > 0) {
      int readLen = stream->readBytes(buffer + offset, min(available, static_cast<size_t>(size) - offset));
      offset += readLen;
      lastReadMs = millis();
    } else if (millis() - lastReadMs > 5000) {
      Serial.println("Audio download timed out");
      free(buffer);
      http.end();
      return false;
    }
    if (pump_) pump_();
    delay(1);
  }

  Serial.printf("Playing audio: %u bytes\n", static_cast<unsigned>(offset));
  M5.Mic.end();
  delay(50);
  if (!M5.Speaker.begin()) {
    Serial.println("Speaker begin failed");
    free(buffer);
    http.end();
    return false;
  }
  M5.Speaker.setVolume(kSpeakerVolume);
  bool ok = M5.Speaker.playWav(buffer, offset, 1, -1, true);
  if (!ok) {
    Serial.println("Speaker playWav failed");
  }
  unsigned long startedMs = millis();
  while (M5.Speaker.isPlaying() && millis() - startedMs < kPlaybackTimeoutMs) {
    M5.update();
    if (pump_) pump_();
    delay(10);
  }
  M5.Speaker.stop();
  M5.Speaker.end();
  free(buffer);
  http.end();
  return ok;
}

bool SpeakerPlayer::playWavBytes(const uint8_t* data, size_t size) {
  if (data == nullptr || size <= kMinWavBytes || size > kMaxWavBytes) {
    Serial.printf("Invalid realtime wav size: %u\n", static_cast<unsigned>(size));
    return false;
  }
  uint8_t* buffer = static_cast<uint8_t*>(ps_malloc(size));
  if (buffer == nullptr) {
    Serial.println("Realtime audio buffer allocation failed");
    return false;
  }
  memcpy(buffer, data, size);
  M5.Mic.end();
  delay(50);
  if (!M5.Speaker.begin()) {
    Serial.println("Speaker begin failed");
    free(buffer);
    return false;
  }
  M5.Speaker.setVolume(kSpeakerVolume);
  bool ok = M5.Speaker.playWav(buffer, size, 1, -1, true);
  unsigned long startedMs = millis();
  while (M5.Speaker.isPlaying() && millis() - startedMs < kPlaybackTimeoutMs) {
    M5.update();
    if (pump_) pump_();
    delay(10);
  }
  M5.Speaker.stop();
  M5.Speaker.end();
  free(buffer);
  return ok;
}

String SpeakerPlayer::absoluteUrl(const String& audioUrl) const {
  if (audioUrl.startsWith("http://") || audioUrl.startsWith("https://")) {
    return audioUrl;
  }
  if (audioUrl.startsWith("/")) {
    return String(GATEWAY_HOST) + audioUrl;
  }
  return String(GATEWAY_HOST) + "/" + audioUrl;
}
