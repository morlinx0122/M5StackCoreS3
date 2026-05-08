#pragma once

#include <Arduino.h>
#include <M5Unified.h>
#include "robot_state.h"

class FaceEngine {
 public:
  void begin();
  void update(RobotState state);

 private:
  M5Canvas canvas_{&M5.Display};
  RobotState lastState_ = RobotState::BOOT;
  unsigned long lastFrameMs_ = 0;
  int frame_ = 0;

  void clear();
  void present();
  void drawShell();
  void drawEyes(uint32_t color, int eyeHeight, int yOffset = 0, bool sparkle = true);
  void drawSmile(uint32_t color, int y, int openness = 0);
  void drawCaption(const char* text, uint32_t color);
  void drawBase(uint32_t eyeColor);
  void drawIdle();
  void drawListening();
  void drawThinking();
  void drawSpeaking();
  void drawSleeping();
  void drawError();
  void drawStatusText(const char* text, uint32_t color);
};
