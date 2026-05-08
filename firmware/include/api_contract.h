#pragma once

namespace ApiPath {
constexpr const char* Health = "/health";
constexpr const char* Register = "/device/register";
constexpr const char* Heartbeat = "/device/heartbeat";
constexpr const char* Status = "/device/status";
constexpr const char* Commands = "/device/%s/commands";
constexpr const char* CommandAck = "/device/%s/commands/%s/ack";
constexpr const char* AudioChat = "/audio/chat";
constexpr const char* AudioTranscribe = "/audio/transcribe";
constexpr const char* AudioWakeChat = "/audio/wake_chat";
}
