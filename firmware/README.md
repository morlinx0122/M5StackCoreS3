# DeskBot CoreS3 Firmware

PlatformIO + Arduino + M5Unified firmware for the M5Stack CoreS3 desktop AI assistant.

## Configure

Edit [include/config.h](include/config.h):

```cpp
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define GATEWAY_HOST "http://192.168.1.100:8000"
```

`GATEWAY_HOST` should point to the machine running the FastAPI gateway.

## Build

```powershell
cd firmware
pio run
```

## Current Behavior

- Connects Wi-Fi.
- Registers with the gateway.
- Sends heartbeat and status logs.
- Polls command endpoint.
- Shows basic animated states.
- Single tap simulates listen/upload/think/speak.
- Double tap returns to idle.
- Long press enters sleep.

