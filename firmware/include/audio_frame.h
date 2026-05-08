#pragma once

#include <Arduino.h>
#include "config.h"

struct AudioFrame {
  int16_t samples[AUDIO_FRAME_SAMPLES];
  size_t count = 0;
  uint32_t timestampMs = 0;
  uint32_t seq = 0;
};
