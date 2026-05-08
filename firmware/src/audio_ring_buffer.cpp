#include "audio_ring_buffer.h"

#include <cstring>
#include <M5Unified.h>

bool AudioRingBuffer::begin() {
  if (frames_ != nullptr) {
    reset();
    return true;
  }

  frames_ = static_cast<AudioFrame*>(ps_malloc(sizeof(AudioFrame) * AUDIO_RING_FRAME_COUNT));
  if (frames_ == nullptr) {
    Serial.println("AudioRingBuffer allocation failed");
    return false;
  }

  reset();
  Serial.printf("AudioRingBuffer ready: %u frames\n", static_cast<unsigned>(AUDIO_RING_FRAME_COUNT));
  return true;
}

void AudioRingBuffer::reset() {
  writeIndex_ = 0;
  frameCount_ = 0;
  latestTimestampMs_ = 0;
  if (frames_ != nullptr) {
    memset(frames_, 0, sizeof(AudioFrame) * AUDIO_RING_FRAME_COUNT);
  }
}

void AudioRingBuffer::push(const int16_t* samples, size_t count, uint32_t timestampMs, uint32_t seq) {
  if (frames_ == nullptr || samples == nullptr || count == 0) {
    return;
  }

  if (count > AUDIO_FRAME_SAMPLES) {
    count = AUDIO_FRAME_SAMPLES;
  }

  AudioFrame& frame = frames_[writeIndex_];
  memcpy(frame.samples, samples, count * sizeof(int16_t));
  frame.count = count;
  frame.timestampMs = timestampMs;
  frame.seq = seq;

  writeIndex_ = (writeIndex_ + 1) % AUDIO_RING_FRAME_COUNT;
  if (frameCount_ < AUDIO_RING_FRAME_COUNT) {
    frameCount_++;
  }
  latestTimestampMs_ = timestampMs;
}

size_t AudioRingBuffer::copyRecent(int16_t* out, size_t maxSamples, uint32_t durationMs) const {
  if (frames_ == nullptr || out == nullptr || maxSamples == 0 || frameCount_ == 0) {
    return 0;
  }

  size_t written = 0;
  size_t oldestIndex = (writeIndex_ + AUDIO_RING_FRAME_COUNT - frameCount_) % AUDIO_RING_FRAME_COUNT;
  for (size_t i = 0; i < frameCount_; ++i) {
    size_t index = (oldestIndex + i) % AUDIO_RING_FRAME_COUNT;
    const AudioFrame& frame = frames_[index];
    if (frame.count == 0) {
      continue;
    }

    if (latestTimestampMs_ >= frame.timestampMs && latestTimestampMs_ - frame.timestampMs > durationMs) {
      continue;
    }

    size_t canCopy = min(frame.count, maxSamples - written);
    memcpy(out + written, frame.samples, canCopy * sizeof(int16_t));
    written += canCopy;
    if (written >= maxSamples) {
      break;
    }
  }

  return written;
}

bool AudioRingBuffer::hasEnough(uint32_t durationMs) const {
  if (frames_ == nullptr || frameCount_ == 0) {
    return false;
  }

  size_t oldestIndex = (writeIndex_ + AUDIO_RING_FRAME_COUNT - frameCount_) % AUDIO_RING_FRAME_COUNT;
  const AudioFrame& oldest = frames_[oldestIndex];
  if (oldest.count == 0 || latestTimestampMs_ < oldest.timestampMs) {
    return false;
  }

  return latestTimestampMs_ - oldest.timestampMs >= durationMs;
}

uint32_t AudioRingBuffer::latestTimestampMs() const {
  return latestTimestampMs_;
}
