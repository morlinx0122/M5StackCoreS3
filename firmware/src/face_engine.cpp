#include "face_engine.h"

#include "ui_theme.h"

void FaceEngine::begin() {
  M5.Display.setRotation(1);
  M5.Display.fillScreen(UiTheme::Background);
  canvas_.setColorDepth(16);
  canvas_.createSprite(M5.Display.width(), M5.Display.height());
  clear();
  present();
}

void FaceEngine::update(RobotState state) {
  unsigned long now = millis();
  if (state == lastState_ && now - lastFrameMs_ < 80) {
    return;
  }

  lastState_ = state;
  lastFrameMs_ = now;
  frame_++;

  switch (state) {
    case RobotState::BOOT:
    case RobotState::WIFI_CONNECTING:
    case RobotState::REGISTERING:
      drawStatusText(robotStateToString(state), UiTheme::Warning);
      break;
    case RobotState::IDLE:
    case RobotState::INTERRUPTED:
    case RobotState::WAKE_LISTENING:
      drawIdle();
      break;
    case RobotState::WAKE_DETECTED:
    case RobotState::RECORDING:
    case RobotState::LISTENING:
    case RobotState::LISTENING_STREAM:
    case RobotState::STT_PARTIAL:
      drawListening();
      break;
    case RobotState::UPLOADING:
    case RobotState::WAITING_REPLY:
    case RobotState::THINKING:
    case RobotState::ACKING:
      drawThinking();
      break;
    case RobotState::SPEAKING:
    case RobotState::SPEAKING_STREAM:
      drawSpeaking();
      break;
    case RobotState::SLEEPING:
      drawSleeping();
      break;
    case RobotState::ERROR_STATE:
      drawError();
      break;
  }

  present();
}

void FaceEngine::clear() {
  canvas_.fillScreen(UiTheme::Background);
}

void FaceEngine::present() {
  canvas_.pushSprite(0, 0);
}

void FaceEngine::drawShell() {
  canvas_.fillRoundRect(18, 22, 284, 196, 28, UiTheme::Panel);
  canvas_.drawRoundRect(18, 22, 284, 196, 28, UiTheme::FaceDim);
  canvas_.drawRoundRect(22, 26, 276, 188, 24, 0x173247);
}

void FaceEngine::drawEyes(uint32_t color, int eyeHeight, int yOffset, bool sparkle) {
  int y = 78 + yOffset + (58 - eyeHeight) / 2;
  int radius = eyeHeight > 22 ? 20 : 8;

  canvas_.fillRoundRect(58, y, 76, eyeHeight, radius, color);
  canvas_.fillRoundRect(186, y, 76, eyeHeight, radius, color);

  if (sparkle && eyeHeight > 24) {
    canvas_.fillCircle(78, y + 14, 5, UiTheme::Text);
    canvas_.fillCircle(206, y + 14, 5, UiTheme::Text);
    canvas_.fillCircle(96, y + 28, 3, 0xB8F5FF);
    canvas_.fillCircle(224, y + 28, 3, 0xB8F5FF);
  }
}

void FaceEngine::drawSmile(uint32_t color, int y, int openness) {
  if (openness > 0) {
    int height = 10 + openness;
    canvas_.fillRoundRect(128, y - height / 2, 64, height, 10, color);
    canvas_.fillRoundRect(140, y - height / 2 + 4, 40, 5, 4, 0xDFFFF5);
    return;
  }

  canvas_.drawArc(160, y, 42, 34, 28, 152, color);
  canvas_.drawArc(160, y + 1, 42, 34, 28, 152, color);
}

void FaceEngine::drawCaption(const char* text, uint32_t color) {
  canvas_.setTextDatum(middle_center);
  canvas_.setTextColor(color, UiTheme::Panel);
  canvas_.drawString(text, 160, 198, &fonts::FreeSans9pt7b);
}

void FaceEngine::drawBase(uint32_t eyeColor) {
  clear();
  drawShell();
  drawEyes(eyeColor, 54);
  canvas_.fillCircle(82, 150, 7, UiTheme::AccentDim);
  canvas_.fillCircle(238, 150, 7, UiTheme::AccentDim);
}

void FaceEngine::drawIdle() {
  int blink = (frame_ % 70 > 64) ? 8 : 54;
  int bob = (frame_ % 30 < 15) ? 0 : 2;
  clear();
  drawShell();
  drawEyes(UiTheme::Face, blink, bob);
  canvas_.fillCircle(82, 151 + bob, 7, UiTheme::AccentDim);
  canvas_.fillCircle(238, 151 + bob, 7, UiTheme::AccentDim);
  drawSmile(UiTheme::Accent, 158 + bob);
}

void FaceEngine::drawListening() {
  drawBase(UiTheme::Accent);
  int wave = frame_ % 18;
  canvas_.drawArc(160, 160, 24 + wave, 20 + wave, 205, 335, UiTheme::Face);
  canvas_.drawArc(160, 160, 46 + wave, 42 + wave, 205, 335, UiTheme::FaceDim);
  drawSmile(UiTheme::Face, 160);
  drawCaption("Listening", UiTheme::MutedText);
}

void FaceEngine::drawThinking() {
  drawBase(UiTheme::Warning);
  canvas_.fillRoundRect(132, 150, 56, 20, 10, UiTheme::Panel);
  for (int i = 0; i < 3; ++i) {
    int phase = (frame_ + i * 5) % 20;
    int pulse = phase < 10 ? 6 + phase / 3 : 9 - (phase - 10) / 3;
    canvas_.fillCircle(140 + i * 20, 160, pulse, UiTheme::Warning);
  }
  drawCaption("Thinking", UiTheme::MutedText);
}

void FaceEngine::drawSpeaking() {
  drawBase(UiTheme::Face);
  int mouthHeight = 8 + ((frame_ % 10) < 5 ? frame_ % 5 : 9 - frame_ % 10) * 5;
  drawSmile(UiTheme::Accent, 158, mouthHeight);
  drawCaption("Speaking", UiTheme::MutedText);
}

void FaceEngine::drawSleeping() {
  clear();
  drawShell();
  drawEyes(UiTheme::FaceDim, 8, 8, false);
  drawSmile(UiTheme::FaceDim, 158);
  canvas_.setTextColor(UiTheme::Face, UiTheme::Background);
  canvas_.setTextDatum(middle_center);
  canvas_.drawString("Zzz", 160, 54, &fonts::FreeSansBold18pt7b);
}

void FaceEngine::drawError() {
  drawBase(UiTheme::Error);
  canvas_.drawLine(126, 158, 194, 158, UiTheme::Error);
  canvas_.drawLine(126, 158, 116, 172, UiTheme::Error);
  canvas_.drawLine(194, 158, 204, 172, UiTheme::Error);
  drawCaption("Offline", UiTheme::Error);
}

void FaceEngine::drawStatusText(const char* text, uint32_t color) {
  clear();
  drawShell();
  drawEyes(color, 28, -8, false);
  canvas_.setTextDatum(middle_center);
  canvas_.setTextColor(color, UiTheme::Panel);
  canvas_.drawString(text, 160, 145, &fonts::FreeSansBold12pt7b);
}
