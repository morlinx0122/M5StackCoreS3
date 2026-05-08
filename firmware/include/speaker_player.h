#pragma once

#include <Arduino.h>
#include <functional>

class SpeakerPlayer {
 public:
  using PumpFn = std::function<void()>;

  bool begin();
  bool downloadAndPlay(const String& audioUrl);
  bool playWavBytes(const uint8_t* data, size_t size);
  // Optional pump invoked frequently during blocking download/playback so the
  // caller (e.g. the WS client) can service its own loop / heartbeat and
  // avoid being killed for inactivity.
  void setPump(PumpFn pump) { pump_ = std::move(pump); }

 private:
  String absoluteUrl(const String& audioUrl) const;
  PumpFn pump_;
};
