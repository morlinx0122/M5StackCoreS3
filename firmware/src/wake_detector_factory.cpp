#include "wake_detector_factory.h"

#include "config.h"
#include "esp_sr_wake_detector.h"
#include "fake_wake_detector.h"

namespace {
FakeWakeDetector fakeWakeDetector;
EspSrWakeDetector espSrWakeDetector;
}

WakeDetector* createWakeDetector() {
#if WAKE_DETECTOR_MODE == WAKE_DETECTOR_MODE_ESP_SR
  return &espSrWakeDetector;
#else
  return &fakeWakeDetector;
#endif
}

WakeDetector* createFallbackWakeDetector() {
  return &fakeWakeDetector;
}
