#include "robot_state.h"

const char* robotStateToString(RobotState state) {
  switch (state) {
    case RobotState::BOOT:
      return "BOOT";
    case RobotState::WIFI_CONNECTING:
      return "WIFI_CONNECTING";
    case RobotState::REGISTERING:
      return "REGISTERING";
    case RobotState::IDLE:
      return "IDLE";
    case RobotState::LISTENING_STREAM:
      return "LISTENING_STREAM";
    case RobotState::STT_PARTIAL:
      return "STT_PARTIAL";
    case RobotState::WAKE_LISTENING:
      return "WAKE_LISTENING";
    case RobotState::WAKE_DETECTED:
      return "WAKE_DETECTED";
    case RobotState::RECORDING:
      return "RECORDING";
    case RobotState::LISTENING:
      return "LISTENING";
    case RobotState::UPLOADING:
      return "UPLOADING";
    case RobotState::WAITING_REPLY:
      return "WAITING_REPLY";
    case RobotState::THINKING:
      return "THINKING";
    case RobotState::SPEAKING_STREAM:
      return "SPEAKING_STREAM";
    case RobotState::INTERRUPTED:
      return "INTERRUPTED";
    case RobotState::SPEAKING:
      return "SPEAKING";
    case RobotState::ACKING:
      return "ACKING";
    case RobotState::SLEEPING:
      return "SLEEPING";
    case RobotState::ERROR_STATE:
      return "ERROR_STATE";
  }
  return "UNKNOWN";
}
