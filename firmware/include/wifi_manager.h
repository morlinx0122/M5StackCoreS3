#pragma once

#include <Arduino.h>

class WiFiManager {
 public:
  void begin();
  void loop();
  bool isConnected() const;
  String localIp() const;

 private:
  unsigned long lastReconnectAttemptMs_ = 0;
  void connect();
};

