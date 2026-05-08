#pragma once

#include <Arduino.h>
#include "audio_frame.h"

class AudioRingBuffer {
 public:
  bool begin();
  void reset();
  void push(const int16_t* samples, size_t count, uint32_t timestampMs, uint32_t seq);
  size_t copyRecent(int16_t* out, size_t maxSamples, uint32_t durationMs) const;
  bool hasEnough(uint32_t durationMs) const;
  uint32_t latestTimestampMs() const;

 private:
  AudioFrame* frames_ = nullptr;
  size_t writeIndex_ = 0;
  size_t frameCount_ = 0;
  uint32_t latestTimestampMs_ = 0;
};
