#pragma once

#include "wake_detector.h"

class EspSrWakeDetector : public WakeDetector {
 public:
  bool begin() override;
  WakeResult process(const int16_t* samples, size_t count) override;
  const char* name() const override;

 private:
  bool ready_ = false;
};
