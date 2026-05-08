#include "fake_wake_detector.h"

#include <M5Unified.h>

bool FakeWakeDetector::begin() {
  triggered_ = false;
  Serial.println("FakeWakeDetector ready");
  return true;
}

WakeResult FakeWakeDetector::process(const int16_t* samples, size_t count) {
  (void)samples;
  (void)count;
  if (!triggered_) {
    WakeResult result;
    result.type = WakeResultType::NONE;
    result.confidence = 0.0f;
    return result;
  }

  triggered_ = false;
  Serial.println("FakeWakeDetector matched");
  WakeResult result;
  result.type = WakeResultType::MATCHED;
  result.confidence = 1.0f;
  return result;
}

void FakeWakeDetector::trigger() {
  triggered_ = true;
}

const char* FakeWakeDetector::name() const {
  return "fake";
}
