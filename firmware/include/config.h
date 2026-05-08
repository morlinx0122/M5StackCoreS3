#pragma once

// ESP32-S3 only supports 2.4GHz Wi-Fi. Do not use a 5GHz-only SSID here.
#define WIFI_SSID "DeepNexus2.4G"
#define WIFI_PASSWORD "Sq055378"

//#define WIFI_SSID "Xiaomi_F199"
//#define WIFI_PASSWORD "1990310Xu"

#define GATEWAY_HOST  "http://192.168.10.125:8000"
#define GATEWAY_WS_HOST "192.168.10.125"
#define GATEWAY_WS_PORT 8000
#define DEVICE_ID "cores3-dev-001"
#define DEVICE_NAME "DeskBot CoreS3"
#define FIRMWARE_VERSION "0.1.0-dev"

#define HEALTH_CHECK_INTERVAL_MS 10000UL
#define HEARTBEAT_INTERVAL_MS 15000UL
#define COMMAND_POLL_INTERVAL_MS 1500UL
#define COMMAND_POLL_WAITING_REPLY_MS 500UL
#define WIFI_RECONNECT_INTERVAL_MS 5000UL
#define THINKING_TIMEOUT_MS 35000UL

#define WAKE_WORD_ENABLED 0
#define WAKE_DETECTOR_MODE_FAKE 0
#define WAKE_DETECTOR_MODE_ESP_SR 1
#define WAKE_DETECTOR_MODE WAKE_DETECTOR_MODE_FAKE
#define WAKE_WORD_LISTEN_INTERVAL_MS 700UL
#define WAKE_WORDS "桌面机器人,小助手,你好机器人,嘿机器人"

// Cloud wake-word streaming (FunASR partial in gateway). 1=enabled, 0=disabled.
// Touch single-tap fallback still works regardless of this flag.
#define CLOUD_WAKE_WATCH_ENABLED 1
// Re-open wake-watch session this many ms after a previous one ended (avoid hammering)
#define CLOUD_WAKE_RESTART_MIN_MS 800UL

#define AUDIO_SAMPLE_RATE 16000
#define AUDIO_RECORD_SECONDS 6
#define AUDIO_FRAME_SAMPLES 512
#define AUDIO_RING_FRAME_COUNT 100
#define AUDIO_PRE_ROLL_MS 800
#define VAD_CHUNK_MS 100
#define VAD_CALIBRATION_MS 200
#define VAD_MIN_RECORD_MS 400
#define VAD_MAX_RECORD_MS 6000
#define VAD_SILENCE_END_MS 350
#define VAD_START_VOICE_MS 100
#define VAD_PRE_ROLL_MS 300
#define VAD_THRESHOLD_MULTIPLIER 2
#define VAD_THRESHOLD_OFFSET 60
#define VAD_MIN_THRESHOLD 120
#define VAD_WAIT_TIMEOUT_MS 5000
