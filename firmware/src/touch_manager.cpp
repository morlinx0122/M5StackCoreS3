#include "touch_manager.h"

TouchEvent TouchManager::update() {
  auto detail = M5.Touch.getDetail();
  bool pressed = detail.isPressed();
  unsigned long now = millis();

  if (pressed && !wasPressed_) {
    pressedAtMs_ = now;
    longPressEmitted_ = false;
    wasPressed_ = pressed;
    return TouchEvent::PRESS_START;
  }

  if (pressed && !longPressEmitted_ && now - pressedAtMs_ > 900) {
    longPressEmitted_ = true;
    wasPressed_ = pressed;
    return TouchEvent::LONG_PRESS;
  }

  if (!pressed && wasPressed_ && !longPressEmitted_) {
    if (now - lastTapMs_ < 350) {
      lastTapMs_ = 0;
      wasPressed_ = pressed;
      return TouchEvent::DOUBLE_TAP;
    }
    lastTapMs_ = now;
    wasPressed_ = pressed;
    return TouchEvent::SINGLE_TAP;
  }

  wasPressed_ = pressed;
  return TouchEvent::NONE;
}
