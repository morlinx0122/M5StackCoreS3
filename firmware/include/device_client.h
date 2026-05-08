#pragma once

#include <Arduino.h>
#include "robot_state.h"

class DeviceClient {
 public:
  explicit DeviceClient(const char* baseUrl);

  bool healthCheck();
  bool registerDevice(const String& ipAddress);
  bool sendHeartbeat(RobotState state);
  bool sendStatus(RobotState state);
  bool pollCommands(String* response = nullptr);
  bool ackCommand(const String& commandId, bool success, unsigned long playedMs = 0, const char* errorCode = nullptr, const char* errorMessage = nullptr);
  bool uploadAudioChat(const uint8_t* wavData, size_t wavSize, RobotState state, String* response = nullptr);
  bool uploadAudioTranscribe(const uint8_t* wavData, size_t wavSize, String* response = nullptr);
  bool uploadAudioWakeChat(const uint8_t* wavData, size_t wavSize, RobotState state, String* response = nullptr);

 private:
  String baseUrl_;
  bool postMultipartAudio(const char* path, const uint8_t* wavData, size_t wavSize, const String& extraFields, String* response);
  bool postJson(const String& path, const String& body, String* response = nullptr);
  bool get(const String& path, String* response = nullptr);
};
