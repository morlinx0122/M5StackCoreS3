#pragma once

#include <Arduino.h>
#include <M5Unified.h>

enum class TouchEvent {
  NONE,
  PRESS_START,
  SINGLE_TAP,
  DOUBLE_TAP,
  LONG_PRESS
};

class TouchManager {
 public:
  TouchEvent update();

 private:
  bool wasPressed_ = false;
  bool longPressEmitted_ = false;
  unsigned long pressedAtMs_ = 0;
  unsigned long lastTapMs_ = 0;
};
