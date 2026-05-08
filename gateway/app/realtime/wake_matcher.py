"""Cloud-based wake word matching for FunASR partial transcripts.

Wake word: "大雷大雷" (repeated da-lei) — chosen for high acoustic redundancy
on noisy ESP32-S3 PDM mic. Repetition + common Mandarin chars greatly improves
SenseVoice recognition robustness vs distinctive but short names.

Strategy:
- Strip SenseVoice metadata tags then punctuation.
- Match on a wide set of homophone variants OR fuzzy regex pattern.
- Cooldown: 5s between detections.
"""
from __future__ import annotations

import re
from time import perf_counter
from typing import Iterable, Optional


# Variants of "大雷大雷" likely produced by SenseVoice on poor audio.
_NAME_VARIANTS: tuple[str, ...] = (
    # Canonical and direct duplications
    "大雷大雷",
    "大雷大磊",
    "大磊大磊",
    "大磊大雷",
    "大蕾大蕾",
    "大累大累",
    "大类大类",
    # Loose homophones of 大 (da/dai/ta)
    "打雷打雷",
    "搭雷搭雷",
    "答雷答雷",
    "答类答类",
    "塔雷塔雷",
    "他雷他雷",
    "他磊他磊",
    "踏雷踏雷",
    # Single occurrence (one da-lei pair) — accept it too if clear
    "大雷",
    "大磊",
    "大蕾",
    "大累",
    "打雷",
    "搭雷",
    "答雷",
    "他雷",
    # Fragmented but recognizable
    "大类大",
    "大磊大",
    "大雷大",
    "雷大雷",
    "磊大磊",
)

_TAG_RE = re.compile(r"<\|[^|>]*\|>")

# Fuzzy patterns for da-lei sound combos.
_FUZZY_SINGLE = re.compile(r"[大打搭答他塔踏嗒达][雷磊蕾累类泪]")
_FUZZY_DOUBLE = re.compile(
    r"[大打搭答他塔踏嗒达][雷磊蕾累类泪][\u4e00-\u9fff]{0,2}[大打搭答他塔踏嗒达][雷磊蕾累类泪]"
)
# Very loose: "大" (or homophone) repeated twice within ~3 chars — caters to
# SenseVoice mishearing the trailing "lei" syllable on noisy audio (杯/咧/肥/门 etc).
_FUZZY_REPEATED_DA = re.compile(
    r"[大打搭答他塔踏嗒达][\u4e00-\u9fff]{0,1}[大打搭答他塔踏嗒达]"
)

_PUNCT_RE = re.compile(r"[\s,，.。!！?？:：;；、~`'\"/()\[\]{}\-_]+")


def normalize(text: str) -> str:
    """Lowercase + strip SenseVoice tags + strip punctuation/whitespace."""
    if not text:
        return ""
    text = _TAG_RE.sub("", text)
    return _PUNCT_RE.sub("", text.lower())


class WakeMatcher:
    """Stateful wake-word detector with cooldown."""

    def __init__(
        self,
        name_variants: Iterable[str] = _NAME_VARIANTS,
        cooldown_sec: float = 5.0,
    ) -> None:
        self._variants = tuple(v.lower() for v in name_variants)
        self._cooldown_sec = cooldown_sec
        self._last_match_at: float = 0.0

    def reset_cooldown(self) -> None:
        self._last_match_at = 0.0

    def match(self, text: str) -> Optional[str]:
        """Return canonical wake phrase '大雷大雷' if matched, else None."""
        norm = normalize(text)
        if not norm:
            return None

        # 1. Exact variant
        for variant in self._variants:
            if variant in norm:
                return self._with_cooldown("大雷大雷")

        # 2. Two adjacent da-lei pairs (strong signal)
        if _FUZZY_DOUBLE.search(norm):
            return self._with_cooldown("大雷大雷")

        # 3. Single da-lei pair fallback
        if _FUZZY_SINGLE.search(norm):
            return self._with_cooldown("大雷大雷")

        # 4. Repeated "大" within ~3 chars — extremely lenient fallback for
        # noisy mic where the trailing "lei" syllable is often misheard.
        if _FUZZY_REPEATED_DA.search(norm):
            return self._with_cooldown("大雷大雷")

        return None

    def _with_cooldown(self, phrase: str) -> Optional[str]:
        now = perf_counter()
        if now - self._last_match_at < self._cooldown_sec:
            return None
        self._last_match_at = now
        return phrase
