#include "esp_sr_wake_detector.h"

#include <M5Unified.h>

bool EspSrWakeDetector::begin() {
  ready_ = false;
  Serial.println("EspSrWakeDetector is not implemented yet");
  return ready_;
}

WakeResult EspSrWakeDetector::process(const int16_t* samples, size_t count) {
  (void)samples;
  (void)count;
  WakeResult result;
  result.type = WakeResultType::NONE;
  result.confidence = 0.0f;
  return result;
}

const char* EspSrWakeDetector::name() const {
  return "esp_sr";
}
