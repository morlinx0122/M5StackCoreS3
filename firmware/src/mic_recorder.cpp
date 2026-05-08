#include "mic_recorder.h"

#include <M5Unified.h>
#include "config.h"

bool MicRecorder::begin() {
  return begin(nullptr);
}

bool MicRecorder::begin(AudioEngine* audioEngine) {
  audioEngine_ = audioEngine;
  sampleCount_ = AUDIO_SAMPLE_RATE * AUDIO_RECORD_SECONDS;
  wavSize_ = 44 + sampleCount_ * sizeof(int16_t);

  pcmBuffer_ = static_cast<int16_t*>(ps_malloc(sampleCount_ * sizeof(int16_t)));
  wavBuffer_ = static_cast<uint8_t*>(ps_malloc(wavSize_));

  if (pcmBuffer_ == nullptr || wavBuffer_ == nullptr) {
    Serial.println("Mic buffer allocation failed");
    return false;
  }

  Serial.printf("Mic ready: %u samples, %u wav bytes\n", static_cast<unsigned>(sampleCount_), static_cast<unsigned>(wavSize_));
  return true;
}

bool MicRecorder::recordFixed() {
  if (pcmBuffer_ == nullptr || wavBuffer_ == nullptr) {
    return false;
  }

  Serial.println("Recording audio...");
  M5.Speaker.end();
  delay(50);
  if (!M5.Mic.begin()) {
    Serial.println("Mic begin failed");
    return false;
  }

  bool ok = M5.Mic.record(pcmBuffer_, sampleCount_, AUDIO_SAMPLE_RATE);
  M5.Mic.end();
  if (!ok) {
    Serial.println("Mic record failed");
    return false;
  }

  uint32_t pcmBytes = sampleCount_ * sizeof(int16_t);
  wavSize_ = 44 + pcmBytes;
  writeWavHeader(wavBuffer_, pcmBytes);
  memcpy(wavBuffer_ + 44, pcmBuffer_, pcmBytes);
  Serial.printf("Recording done: %u bytes\n", static_cast<unsigned>(wavSize_));
  return true;
}

bool MicRecorder::recordUntilRelease() {
  if (pcmBuffer_ == nullptr || wavBuffer_ == nullptr) {
    return false;
  }

  M5.Speaker.end();
  delay(50);
  if (!M5.Mic.begin()) {
    Serial.println("Mic begin failed");
    return false;
  }

  constexpr size_t chunkSamples = AUDIO_SAMPLE_RATE / 10;
  constexpr size_t minSamples = AUDIO_SAMPLE_RATE / 2;
  size_t recordedSamples = 0;
  Serial.println("Recording audio until touch release...");

  while (recordedSamples < sampleCount_) {
    M5.update();
    bool pressed = M5.Touch.getDetail().isPressed();
    if (!pressed && recordedSamples >= minSamples) {
      break;
    }

    size_t remaining = sampleCount_ - recordedSamples;
    size_t samplesToRead = min(chunkSamples, remaining);
    bool ok = M5.Mic.record(pcmBuffer_ + recordedSamples, samplesToRead, AUDIO_SAMPLE_RATE);
    if (!ok) {
      M5.Mic.end();
      Serial.println("Mic record chunk failed");
      return false;
    }
    recordedSamples += samplesToRead;
    delay(1);
  }

  M5.Mic.end();
  uint32_t pcmBytes = recordedSamples * sizeof(int16_t);
  wavSize_ = 44 + pcmBytes;
  writeWavHeader(wavBuffer_, pcmBytes);
  memcpy(wavBuffer_ + 44, pcmBuffer_, pcmBytes);
  Serial.printf("Recording done: %u samples, %u bytes\n", static_cast<unsigned>(recordedSamples), static_cast<unsigned>(wavSize_));
  return recordedSamples >= minSamples;
}

bool MicRecorder::recordVad() {
  if (pcmBuffer_ == nullptr || wavBuffer_ == nullptr) {
    return false;
  }

  bool usingAudioEngine = audioEngine_ != nullptr && audioEngine_->isReady();
  if (!usingAudioEngine) {
    M5.Speaker.end();
    delay(50);
    if (!M5.Mic.begin()) {
      Serial.println("Mic begin failed");
      return false;
    }
  }

  constexpr size_t chunkSamples = AUDIO_SAMPLE_RATE * VAD_CHUNK_MS / 1000;
  constexpr size_t calibrationChunks = VAD_CALIBRATION_MS / VAD_CHUNK_MS;
  constexpr size_t minRecordSamples = AUDIO_SAMPLE_RATE * VAD_MIN_RECORD_MS / 1000;
  constexpr size_t maxRecordSamples = AUDIO_SAMPLE_RATE * VAD_MAX_RECORD_MS / 1000;
  constexpr size_t silenceEndSamples = AUDIO_SAMPLE_RATE * VAD_SILENCE_END_MS / 1000;
  constexpr size_t startVoiceSamples = AUDIO_SAMPLE_RATE * VAD_START_VOICE_MS / 1000;
  constexpr size_t preRollSamples = AUDIO_SAMPLE_RATE * AUDIO_PRE_ROLL_MS / 1000;
  constexpr size_t waitTimeoutSamples = AUDIO_SAMPLE_RATE * VAD_WAIT_TIMEOUT_MS / 1000;

  size_t recordedSamples = 0;
  size_t liveSamplesRead = 0;
  size_t liveChunksRead = 0;
  size_t speechStartSample = 0;
  size_t voicedSamples = 0;
  size_t silenceSamples = 0;
  uint32_t noiseTotal = 0;
  uint32_t noiseLevel = 0;
  uint32_t threshold = VAD_MIN_THRESHOLD;
  bool speechStarted = false;

  Serial.println("Recording audio with VAD...");
  if (usingAudioEngine && audioEngine_->hasPreRoll(AUDIO_PRE_ROLL_MS)) {
    size_t maxPreRollSamples = min(preRollSamples, sampleCount_);
    recordedSamples = audioEngine_->copyPreRoll(pcmBuffer_, maxPreRollSamples, AUDIO_PRE_ROLL_MS);
    Serial.printf("AudioEngine pre-roll copied: %u samples\n", static_cast<unsigned>(recordedSamples));
  }

  while (recordedSamples + chunkSamples <= sampleCount_ && recordedSamples < maxRecordSamples) {
    M5.update();

    bool ok = usingAudioEngine
      ? audioEngine_->readSamples(pcmBuffer_ + recordedSamples, chunkSamples) == chunkSamples
      : M5.Mic.record(pcmBuffer_ + recordedSamples, chunkSamples, AUDIO_SAMPLE_RATE);
    if (!ok) {
      if (!usingAudioEngine) {
        M5.Mic.end();
      }
      Serial.println("Mic record chunk failed");
      return false;
    }

    uint32_t level = averageAbsLevel(pcmBuffer_ + recordedSamples, chunkSamples);
    recordedSamples += chunkSamples;
    liveSamplesRead += chunkSamples;
    liveChunksRead++;

    if (!speechStarted && liveChunksRead <= calibrationChunks) {
      noiseTotal += level;
      noiseLevel = noiseTotal / liveChunksRead;
      uint32_t dynamicThreshold = noiseLevel * VAD_THRESHOLD_MULTIPLIER + VAD_THRESHOLD_OFFSET;
      threshold = dynamicThreshold > VAD_MIN_THRESHOLD ? dynamicThreshold : VAD_MIN_THRESHOLD;
      Serial.printf("VAD calibrating: level=%u noise=%u threshold=%u\n",
                    static_cast<unsigned>(level),
                    static_cast<unsigned>(noiseLevel),
                    static_cast<unsigned>(threshold));
      continue;
    }

    bool voiced = level >= threshold;
    Serial.printf("VAD chunk: level=%u threshold=%u voiced=%d started=%d\n",
                  static_cast<unsigned>(level),
                  static_cast<unsigned>(threshold),
                  voiced,
                  speechStarted);
    if (!speechStarted) {
      if (voiced) {
        voicedSamples += chunkSamples;
        if (voicedSamples >= startVoiceSamples) {
          speechStarted = true;
          size_t voiceStart = recordedSamples > voicedSamples ? recordedSamples - voicedSamples : 0;
          speechStartSample = voiceStart > preRollSamples ? voiceStart - preRollSamples : 0;
          silenceSamples = 0;
          Serial.printf("VAD speech start: level=%u threshold=%u\n",
                        static_cast<unsigned>(level),
                        static_cast<unsigned>(threshold));
        }
      } else {
        voicedSamples = 0;
        if (liveSamplesRead > waitTimeoutSamples) {
          Serial.println("VAD timeout waiting for speech");
          break;
        }
      }
      continue;
    }

    if (voiced) {
      silenceSamples = 0;
    } else {
      silenceSamples += chunkSamples;
      if (recordedSamples - speechStartSample >= minRecordSamples && silenceSamples >= silenceEndSamples) {
        Serial.printf("VAD speech end: silence=%u ms\n",
                      static_cast<unsigned>(silenceSamples * 1000 / AUDIO_SAMPLE_RATE));
        break;
      }
    }

    delay(1);
  }

  if (!usingAudioEngine) {
    M5.Mic.end();
  }

  if (!speechStarted || recordedSamples - speechStartSample < minRecordSamples) {
    Serial.printf("VAD recording too short: started=%d samples=%u\n",
                  speechStarted,
                  static_cast<unsigned>(recordedSamples));
    return false;
  }

  size_t savedSamples = recordedSamples - speechStartSample;
  uint32_t pcmBytes = savedSamples * sizeof(int16_t);
  wavSize_ = 44 + pcmBytes;
  writeWavHeader(wavBuffer_, pcmBytes);
  memcpy(wavBuffer_ + 44, pcmBuffer_ + speechStartSample, pcmBytes);
  Serial.printf("VAD recording done: %u saved samples, %u bytes\n",
                static_cast<unsigned>(savedSamples),
                static_cast<unsigned>(wavSize_));
  return true;
}

const uint8_t* MicRecorder::wavData() const {
  return wavBuffer_;
}

size_t MicRecorder::wavSize() const {
  return wavSize_;
}

uint32_t MicRecorder::averageAbsLevel(const int16_t* samples, size_t count) const {
  uint64_t total = 0;
  for (size_t i = 0; i < count; ++i) {
    int32_t sample = samples[i];
    total += sample < 0 ? -sample : sample;
  }
  return count == 0 ? 0 : static_cast<uint32_t>(total / count);
}

void MicRecorder::writeWavHeader(uint8_t* header, uint32_t pcmBytes) const {
  uint32_t sampleRate = AUDIO_SAMPLE_RATE;
  uint16_t channels = 1;
  uint16_t bitsPerSample = 16;
  uint32_t byteRate = sampleRate * channels * bitsPerSample / 8;
  uint16_t blockAlign = channels * bitsPerSample / 8;
  uint32_t riffSize = 36 + pcmBytes;

  memcpy(header + 0, "RIFF", 4);
  memcpy(header + 4, &riffSize, 4);
  memcpy(header + 8, "WAVE", 4);
  memcpy(header + 12, "fmt ", 4);
  uint32_t fmtSize = 16;
  uint16_t audioFormat = 1;
  memcpy(header + 16, &fmtSize, 4);
  memcpy(header + 20, &audioFormat, 2);
  memcpy(header + 22, &channels, 2);
  memcpy(header + 24, &sampleRate, 4);
  memcpy(header + 28, &byteRate, 4);
  memcpy(header + 32, &blockAlign, 2);
  memcpy(header + 34, &bitsPerSample, 2);
  memcpy(header + 36, "data", 4);
  memcpy(header + 40, &pcmBytes, 4);
}
