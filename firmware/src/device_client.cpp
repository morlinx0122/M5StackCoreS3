#include "device_client.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include "api_contract.h"
#include "config.h"

DeviceClient::DeviceClient(const char* baseUrl) : baseUrl_(baseUrl) {}

bool DeviceClient::healthCheck() {
  String response;
  bool ok = get(ApiPath::Health, &response);
  Serial.printf("Gateway health: %s\n", ok ? "ok" : "failed");
  return ok;
}

bool DeviceClient::registerDevice(const String& ipAddress) {
  StaticJsonDocument<256> doc;
  doc["device_id"] = DEVICE_ID;
  doc["name"] = DEVICE_NAME;
  doc["firmware_version"] = FIRMWARE_VERSION;
  doc["hardware_model"] = "m5stack-cores3";
  doc["ip_address"] = ipAddress;

  String body;
  serializeJson(doc, body);
  return postJson(ApiPath::Register, body);
}

bool DeviceClient::sendHeartbeat(RobotState state) {
  StaticJsonDocument<256> doc;
  doc["device_id"] = DEVICE_ID;
  doc["state"] = robotStateToString(state);
  doc["rssi"] = WiFi.RSSI();
  doc["free_heap"] = ESP.getFreeHeap();

  String body;
  serializeJson(doc, body);
  return postJson(ApiPath::Heartbeat, body);
}

bool DeviceClient::sendStatus(RobotState state) {
  StaticJsonDocument<256> doc;
  doc["device_id"] = DEVICE_ID;
  doc["state"] = robotStateToString(state);
  doc["rssi"] = WiFi.RSSI();
  doc["free_heap"] = ESP.getFreeHeap();

  String body;
  serializeJson(doc, body);
  return postJson(ApiPath::Status, body);
}

bool DeviceClient::pollCommands(String* response) {
  char path[96];
  snprintf(path, sizeof(path), ApiPath::Commands, DEVICE_ID);
  String localResponse;
  bool ok = get(path, &localResponse);
  if (ok) {
    Serial.printf("Commands: %s\n", localResponse.c_str());
    if (response != nullptr) {
      *response = localResponse;
    }
  }
  return ok;
}

bool DeviceClient::ackCommand(const String& commandId, bool success, unsigned long playedMs, const char* errorCode, const char* errorMessage) {
  if (commandId.isEmpty()) {
    return false;
  }

  char path[128];
  snprintf(path, sizeof(path), ApiPath::CommandAck, DEVICE_ID, commandId.c_str());

  JsonDocument doc;
  doc["status"] = success ? "success" : "failed";
  doc["played_ms"] = playedMs;
  if (!success) {
    doc["error_code"] = errorCode != nullptr ? errorCode : "COMMAND_FAILED";
    doc["error_message"] = errorMessage != nullptr ? errorMessage : "";
  }

  String body;
  serializeJson(doc, body);
  bool ok = postJson(path, body);
  Serial.printf("ACK command %s -> %s\n", commandId.c_str(), ok ? "ok" : "failed");
  return ok;
}

bool DeviceClient::uploadAudioChat(const uint8_t* wavData, size_t wavSize, RobotState state, String* response) {
  String fields;
  fields += "--";
  fields += "----DeskBotCoreS3Boundary";
  fields += "\r\n";
  fields += "Content-Disposition: form-data; name=\"device_id\"\r\n\r\n";
  fields += DEVICE_ID;
  fields += "\r\n--";
  fields += "----DeskBotCoreS3Boundary";
  fields += "\r\n";
  fields += "Content-Disposition: form-data; name=\"state\"\r\n\r\n";
  fields += robotStateToString(state);
  fields += "\r\n";

  return postMultipartAudio(ApiPath::AudioChat, wavData, wavSize, fields, response);
}

bool DeviceClient::uploadAudioTranscribe(const uint8_t* wavData, size_t wavSize, String* response) {
  String fields;
  fields += "--";
  fields += "----DeskBotCoreS3Boundary";
  fields += "\r\n";
  fields += "Content-Disposition: form-data; name=\"language\"\r\n\r\n";
  fields += "zh";
  fields += "\r\n";

  return postMultipartAudio(ApiPath::AudioTranscribe, wavData, wavSize, fields, response);
}

bool DeviceClient::uploadAudioWakeChat(const uint8_t* wavData, size_t wavSize, RobotState state, String* response) {
  String fields;
  fields += "--";
  fields += "----DeskBotCoreS3Boundary";
  fields += "\r\n";
  fields += "Content-Disposition: form-data; name=\"device_id\"\r\n\r\n";
  fields += DEVICE_ID;
  fields += "\r\n--";
  fields += "----DeskBotCoreS3Boundary";
  fields += "\r\n";
  fields += "Content-Disposition: form-data; name=\"state\"\r\n\r\n";
  fields += robotStateToString(state);
  fields += "\r\n";

  return postMultipartAudio(ApiPath::AudioWakeChat, wavData, wavSize, fields, response);
}

bool DeviceClient::postMultipartAudio(const char* path, const uint8_t* wavData, size_t wavSize, const String& extraFields, String* response) {
  if (WiFi.status() != WL_CONNECTED || wavData == nullptr || wavSize == 0) {
    return false;
  }

  const String boundary = "----DeskBotCoreS3Boundary";
  String head = extraFields;
  head += "--" + boundary + "\r\n";
  head += "Content-Disposition: form-data; name=\"audio\"; filename=\"recording.wav\"\r\n";
  head += "Content-Type: audio/wav\r\n\r\n";

  String tail = "\r\n--" + boundary + "--\r\n";
  size_t bodySize = head.length() + wavSize + tail.length();
  uint8_t* body = static_cast<uint8_t*>(malloc(bodySize));
  if (body == nullptr) {
    Serial.println("Audio upload body allocation failed");
    return false;
  }

  memcpy(body, head.c_str(), head.length());
  memcpy(body + head.length(), wavData, wavSize);
  memcpy(body + head.length() + wavSize, tail.c_str(), tail.length());

  HTTPClient http;
  http.setTimeout(65000);
  String url = baseUrl_ + path;
  Serial.printf("HTTP POST audio url=%s\n", url.c_str());
  http.begin(url);
  http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);

  int code = http.POST(body, bodySize);
  bool ok = code >= 200 && code < 300;
  if (response != nullptr) {
    *response = http.getString();
  }

  Serial.printf("POST %s audio=%u bytes -> %d\n", path, static_cast<unsigned>(wavSize), code);
  http.end();
  free(body);
  return ok;
}

bool DeviceClient::postJson(const String& path, const String& body, String* response) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  HTTPClient http;
  http.setTimeout(5000);
  String url = baseUrl_ + path;
  Serial.printf("HTTP POST url=%s body=%s\n", url.c_str(), body.c_str());
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  int code = http.POST(body);
  bool ok = code >= 200 && code < 300;
  if (response != nullptr) {
    *response = http.getString();
  }
  Serial.printf("POST %s -> %d\n", path.c_str(), code);
  http.end();
  return ok;
}

bool DeviceClient::get(const String& path, String* response) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  HTTPClient http;
  http.setTimeout(5000);
  String url = baseUrl_ + path;
  Serial.printf("HTTP GET url=%s\n", url.c_str());
  http.begin(url);

  int code = http.GET();
  bool ok = code >= 200 && code < 300;
  if (response != nullptr) {
    *response = http.getString();
  }
  Serial.printf("GET %s -> %d\n", path.c_str(), code);
  http.end();
  return ok;
}
