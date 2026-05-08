#pragma once

#include "device_client.h"
#include "audio_engine.h"
#include "face_engine.h"
#include "mic_recorder.h"
#include "robot_state.h"
#include "realtime_ws_client.h"
#include "speaker_player.h"
#include "touch_manager.h"
#include "wake_detector.h"
#include "wifi_manager.h"

class AppController {
 public:
  AppController();
  void begin();
  void loop();

 private:
  WiFiManager wifi_;
  DeviceClient deviceClient_;
  RealtimeWsClient realtimeWs_;
  AudioEngine audioEngine_;
  WakeDetector* wakeDetector_ = nullptr;
  FaceEngine face_;
  MicRecorder mic_;
  SpeakerPlayer speaker_;
  TouchManager touch_;
  RobotState state_ = RobotState::BOOT;
  bool registered_ = false;
  unsigned long lastHealthCheckMs_ = 0;
  unsigned long lastHeartbeatMs_ = 0;
  unsigned long lastCommandPollMs_ = 0;
  unsigned long lastWakeListenMs_ = 0;
  unsigned long simulatedStateStartedMs_ = 0;
  String realtimeSessionId_;
  // Cloud wake-watch (always-on streaming to gateway for wake word detection)
  bool wakeWatchActive_ = false;
  String wakeWatchSessionId_;
  unsigned long wakeWatchEndedAtMs_ = 0;
  // Deferred trigger: cloud-wake callback runs in WS task context; flagging here
  // lets the main loop run runAudioChat() safely without re-entering the WS stack.
  volatile bool pendingCloudWakeChat_ = false;

  void setState(RobotState state);
  void handleConnection();
  void handleTouch();
  void handleTimers();
  void handleWakeWord();
  void handleWakeWatch();
  bool containsWakeWord(const String& text) const;
  void runAudioChat();
  bool runRealtimeVoiceSession();
  void configureRealtimeCallbacks();
  void onWakeDetectedFromCloud(const String& sessionId, const String& matched);
  void playRealtimeAudioChunk(const String& sessionId, int chunkIndex, const String& audioUrl, const String& text, bool isFinal);
  void applyRealtimeState(const String& state);
  void submitRecordedAudioChat();
};
