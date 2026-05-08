#include "audio_engine.h"

#include <cstring>
#include <M5Unified.h>
#include <esp_heap_caps.h>
#include "config.h"

bool AudioEngine::begin() {
  if (ready_) {
    return true;
  }

  if (!ringBuffer_.begin()) {
    return false;
  }

  if (!configureMic()) {
    Serial.println("AudioEngine mic config failed");
    return false;
  }

  ready_ = M5.Mic.begin();
  if (!ready_) {
    Serial.println("AudioEngine mic begin failed");
    return false;
  }

  latestFrameCount_ = 0;
  latestFrameTs_ = 0;
  Serial.println("AudioEngine ready");
  return true;
}

void AudioEngine::end() {
  if (!ready_) {
    return;
  }

  stopContinuousCapture();
  M5.Mic.end();
  ready_ = false;
  latestFrameCount_ = 0;
  Serial.println("AudioEngine stopped");
}

bool AudioEngine::startContinuousCapture() {
  if (!ready_) {
    return false;
  }
  if (captureRunning_) {
    return true;
  }
  // ~1.6s buffer @ 16kHz mono PCM16 = 51200 bytes; round up.
  captureRb_ = xRingbufferCreate(64 * 1024, RINGBUF_TYPE_BYTEBUF);
  if (captureRb_ == nullptr) {
    Serial.println("AudioEngine ringbuf alloc failed");
    return false;
  }
  captureRunning_ = true;
  captureTaskAlive_ = true;
  BaseType_t res = xTaskCreatePinnedToCore(
      captureTaskTrampoline, "audioCap", 6144, this, 2, &captureTask_, 1);
  if (res != pdPASS) {
    Serial.println("AudioEngine capture task create failed");
    captureRunning_ = false;
    captureTaskAlive_ = false;
    vRingbufferDelete(captureRb_);
    captureRb_ = nullptr;
    return false;
  }
  Serial.println("AudioEngine continuous capture started");
  return true;
}

void AudioEngine::stopContinuousCapture() {
  if (!captureRunning_) {
    return;
  }
  captureRunning_ = false;
  // Wait for task to fully exit. Must be longer than one record() chunk
  // (~100ms) plus the trailing isRecording() drain to ensure DMA has stopped
  // touching the heap-allocated chunk buffer before we let it be freed.
  unsigned long deadline = millis() + 1500;
  while (captureTaskAlive_ && millis() < deadline) {
    delay(10);
  }
  captureTask_ = nullptr;
  if (captureRb_ != nullptr) {
    vRingbufferDelete(captureRb_);
    captureRb_ = nullptr;
  }
  Serial.println("AudioEngine continuous capture stopped");
}

void AudioEngine::captureTaskTrampoline(void* arg) {
  static_cast<AudioEngine*>(arg)->captureTaskRun();
  vTaskDelete(nullptr);
}

void AudioEngine::captureTaskRun() {
  // 100ms chunks @ 16kHz mono => 1600 samples, 3200 bytes.
  static constexpr size_t CAPTURE_CHUNK_SAMPLES = 1600;
  // Stack-allocated for performance; safety relies on never returning from
  // this function while M5.Mic.isRecording() is still true.
  int16_t chunk[CAPTURE_CHUNK_SAMPLES];
  while (captureRunning_) {
    if (!M5.Mic.record(chunk, CAPTURE_CHUNK_SAMPLES, AUDIO_SAMPLE_RATE)) {
      vTaskDelay(pdMS_TO_TICKS(5));
      continue;
    }
    // Wait for this chunk to finish recording. Do NOT short-circuit on
    // captureRunning_: we must wait for DMA to release the chunk buffer
    // before we either reuse it next iteration or exit the task.
    while (M5.Mic.isRecording()) {
      vTaskDelay(pdMS_TO_TICKS(2));
    }
    if (!captureRunning_) break;
    // Push to ringbuffer; if full, drop oldest to keep latency bounded.
    size_t freeSize = xRingbufferGetCurFreeSize(captureRb_);
    if (freeSize < sizeof(chunk) + 16) {
      size_t discardLen = 0;
      void* old = xRingbufferReceiveUpTo(captureRb_, &discardLen, 0, sizeof(chunk));
      if (old != nullptr) {
        vRingbufferReturnItem(captureRb_, old);
      }
    }
    BaseType_t sent = xRingbufferSend(captureRb_, chunk, sizeof(chunk), 0);
    (void)sent;
  }
  // Final safety: drain any in-flight DMA before allowing the stack frame
  // (and chunk[]) to disappear when the task exits.
  while (M5.Mic.isRecording()) {
    vTaskDelay(pdMS_TO_TICKS(2));
  }
  captureTaskAlive_ = false;
}

size_t AudioEngine::popContinuous(int16_t* out, size_t maxSamples) {
  if (captureRb_ == nullptr || out == nullptr || maxSamples == 0) {
    return 0;
  }
  size_t maxBytes = maxSamples * sizeof(int16_t);
  size_t totalBytes = 0;
  while (totalBytes < maxBytes) {
    size_t recvLen = 0;
    void* item = xRingbufferReceiveUpTo(
        captureRb_, &recvLen, 0, maxBytes - totalBytes);
    if (item == nullptr) {
      break;
    }
    memcpy(reinterpret_cast<uint8_t*>(out) + totalBytes, item, recvLen);
    vRingbufferReturnItem(captureRb_, item);
    totalBytes += recvLen;
  }
  return totalBytes / sizeof(int16_t);
}

void AudioEngine::loop() {
  if (!ready_) {
    return;
  }

  if (readSamples(loopFrame_, AUDIO_FRAME_SAMPLES) == 0) {
    Serial.println("AudioEngine frame read failed");
  }
}

bool AudioEngine::isReady() const {
  return ready_;
}

size_t AudioEngine::readSamples(int16_t* out, size_t maxSamples) {
  if (!ready_ || out == nullptr || maxSamples == 0) {
    return 0;
  }

  bool ok = M5.Mic.record(out, maxSamples, AUDIO_SAMPLE_RATE);
  if (!ok) {
    return 0;
  }

  if (!waitForRecording(maxSamples, AUDIO_SAMPLE_RATE)) {
    return 0;
  }

  rememberFrame(out, maxSamples);
  return maxSamples;
}

size_t AudioEngine::readLatestFrame(int16_t* out, size_t maxSamples) const {
  if (!ready_ || out == nullptr || maxSamples == 0 || latestFrameCount_ == 0) {
    return 0;
  }

  size_t count = min(maxSamples, latestFrameCount_);
  memcpy(out, latestFrame_, count * sizeof(int16_t));
  return count;
}

size_t AudioEngine::copyPreRoll(int16_t* out, size_t maxSamples, uint32_t durationMs) const {
  return ringBuffer_.copyRecent(out, maxSamples, durationMs);
}

bool AudioEngine::hasPreRoll(uint32_t durationMs) const {
  return ringBuffer_.hasEnough(durationMs);
}

uint32_t AudioEngine::latestFrameSeq() const {
  return latestFrameSeq_;
}

bool AudioEngine::configureMic() {
  auto micCfg = M5.Mic.config();
  micCfg.sample_rate = AUDIO_SAMPLE_RATE;
  micCfg.stereo = false;
  micCfg.magnification = 16;          // boost low-volume PDM mic input (CoreS3 ES7210)
  micCfg.noise_filter_level = 0;      // disable filter so we keep speech detail
  M5.Mic.config(micCfg);
  return true;
}

bool AudioEngine::waitForRecording(size_t sampleCount, uint32_t sampleRate) const {
  if (sampleRate == 0) {
    return false;
  }

  uint32_t expectedMs = static_cast<uint32_t>((sampleCount * 1000UL + sampleRate - 1) / sampleRate);
  if (expectedMs == 0) {
    expectedMs = 1;
  }

  delay(expectedMs + 5);
  unsigned long deadline = millis() + expectedMs + 500;
  while (M5.Mic.isRecording()) {
    if (millis() > deadline) {
      Serial.println("AudioEngine mic wait timeout");
      return false;
    }
    delay(1);
  }

  return true;
}

void AudioEngine::rememberFrame(const int16_t* samples, size_t count) {
  if (samples == nullptr || count == 0) {
    return;
  }

  size_t copyCount = min(count, static_cast<size_t>(AUDIO_FRAME_SAMPLES));
  memcpy(latestFrame_, samples, copyCount * sizeof(int16_t));
  latestFrameCount_ = copyCount;
  latestFrameTs_ = millis();
  latestFrameSeq_++;
  ringBuffer_.push(latestFrame_, latestFrameCount_, latestFrameTs_, latestFrameSeq_);
}
