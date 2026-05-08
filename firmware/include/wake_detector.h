#pragma once

#include <Arduino.h>

enum class WakeResultType {
  NONE,
  MATCHED
};

struct WakeResult {
  WakeResultType type = WakeResultType::NONE;
  float confidence = 0.0f;
};

class WakeDetector {
 public:
  virtual ~WakeDetector() = default;
  virtual bool begin() = 0;
  virtual WakeResult process(const int16_t* samples, size_t count) = 0;
  virtual void trigger();
  virtual const char* name() const = 0;
};
