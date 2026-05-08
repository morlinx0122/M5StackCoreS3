#pragma once

#include "wake_detector.h"

class FakeWakeDetector : public WakeDetector {
 public:
  bool begin() override;
  WakeResult process(const int16_t* samples, size_t count) override;
  void trigger() override;
  const char* name() const override;

 private:
  bool triggered_ = false;
};
