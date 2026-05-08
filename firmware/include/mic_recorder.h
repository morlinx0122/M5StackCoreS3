#pragma once

#include <Arduino.h>
#include "audio_engine.h"

class MicRecorder {
 public:
  bool begin();
  bool begin(AudioEngine* audioEngine);
  bool recordFixed();
  bool recordUntilRelease();
  bool recordVad();
  const uint8_t* wavData() const;
  size_t wavSize() const;

 private:
  int16_t* pcmBuffer_ = nullptr;
  uint8_t* wavBuffer_ = nullptr;
  AudioEngine* audioEngine_ = nullptr;
  size_t sampleCount_ = 0;
  size_t wavSize_ = 0;

  uint32_t averageAbsLevel(const int16_t* samples, size_t count) const;
  void writeWavHeader(uint8_t* header, uint32_t pcmBytes) const;
};
