#pragma once

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/ringbuf.h>
#include "audio_ring_buffer.h"

class AudioEngine {
 public:
  bool begin();
  void end();
  void loop();
  bool isReady() const;

  size_t readSamples(int16_t* out, size_t maxSamples);
  size_t readLatestFrame(int16_t* out, size_t maxSamples) const;
  size_t copyPreRoll(int16_t* out, size_t maxSamples, uint32_t durationMs) const;
  bool hasPreRoll(uint32_t durationMs) const;
  uint32_t latestFrameSeq() const;

  // Continuous capture mode (FreeRTOS task pinned to core 0).
  // Required for low-latency wake_watch to avoid sample loss between record() calls.
  bool startContinuousCapture();
  void stopContinuousCapture();
  bool isContinuousCapturing() const { return captureRunning_; }
  // Non-blocking pop of up to maxSamples samples from the continuous ringbuffer.
  size_t popContinuous(int16_t* out, size_t maxSamples);

 private:
  bool ready_ = false;
  int16_t loopFrame_[AUDIO_FRAME_SAMPLES] = {};
  int16_t latestFrame_[AUDIO_FRAME_SAMPLES] = {};
  size_t latestFrameCount_ = 0;
  uint32_t latestFrameTs_ = 0;
  uint32_t latestFrameSeq_ = 0;
  AudioRingBuffer ringBuffer_;

  // Continuous capture state
  TaskHandle_t captureTask_ = nullptr;
  RingbufHandle_t captureRb_ = nullptr;
  volatile bool captureRunning_ = false;
  volatile bool captureTaskAlive_ = false;

  bool configureMic();
  bool waitForRecording(size_t sampleCount, uint32_t sampleRate) const;
  void rememberFrame(const int16_t* samples, size_t count);

  static void captureTaskTrampoline(void* arg);
  void captureTaskRun();
};
