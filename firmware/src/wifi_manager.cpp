#include "wifi_manager.h"

#include <WiFi.h>
#include "config.h"

void WiFiManager::begin() {
  WiFi.mode(WIFI_STA);
  connect();
}

void WiFiManager::loop() {
  static bool printedConnectedInfo = false;
  if (isConnected()) {
    if (!printedConnectedInfo) {
      printedConnectedInfo = true;
      Serial.printf(
        "Wi-Fi connected SSID=%s IP=%s gateway=%s dns=%s rssi=%d\n",
        WIFI_SSID,
        WiFi.localIP().toString().c_str(),
        WiFi.gatewayIP().toString().c_str(),
        WiFi.dnsIP().toString().c_str(),
        WiFi.RSSI());
    }
    return;
  }

  printedConnectedInfo = false;

  unsigned long now = millis();
  if (now - lastReconnectAttemptMs_ >= WIFI_RECONNECT_INTERVAL_MS) {
    connect();
  }
}

bool WiFiManager::isConnected() const {
  return WiFi.status() == WL_CONNECTED;
}

String WiFiManager::localIp() const {
  if (!isConnected()) {
    return "";
  }
  return WiFi.localIP().toString();
}

void WiFiManager::connect() {
  lastReconnectAttemptMs_ = millis();
  Serial.printf("Connecting Wi-Fi SSID=%s\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}
