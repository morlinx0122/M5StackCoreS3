from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class FastIntentResult:
    intent: str
    assistant_text: str
    emotion: str = "happy"
    face_state: str = "SPEAKING"
    cached_audio_key: str | None = None


def route_fast_intent(user_text: str, timezone_name: str = "Asia/Shanghai") -> FastIntentResult | None:
    text = normalize_text(user_text)
    if not text:
        return None

    if _is_time_query(text):
        now = datetime.now(ZoneInfo(timezone_name))
        return FastIntentResult(
            intent="get_time",
            assistant_text=f"现在是{now.hour}点{now.minute:02d}分。",
            cached_audio_key=None,
        )

    reminder = _parse_reminder(text)
    if reminder is not None:
        minutes, thing = reminder
        if thing:
            reply = f"好的，我会在{minutes}分钟后提醒你{thing}。"
        else:
            reply = f"好的，我会在{minutes}分钟后提醒你。"
        return FastIntentResult(intent="create_reminder", assistant_text=reply, cached_audio_key="ok_saved")

    pomodoro = _parse_pomodoro(text)
    if pomodoro is not None:
        return FastIntentResult(
            intent="start_pomodoro",
            assistant_text=f"好的，{pomodoro}分钟番茄钟开始。",
            cached_audio_key="pomodoro_started",
        )

    if any(keyword in text for keyword in ("你睡觉吧", "进入待机", "休息吧", "睡眠模式")):
        return FastIntentResult(
            intent="sleep",
            assistant_text="好的，我先待机。",
            face_state="SLEEPING",
            cached_audio_key="ok_saved",
        )

    if any(keyword in text for keyword in ("停止播放", "停一下", "别说了", "暂停播放")):
        return FastIntentResult(
            intent="stop",
            assistant_text="好的，已经停止。",
            face_state="IDLE",
            cached_audio_key="ok_saved",
        )

    if any(keyword in text for keyword in ("再说一遍", "重复一遍", "重说")):
        return FastIntentResult(
            intent="repeat",
            assistant_text="好的，我再说一遍。",
            cached_audio_key="ok_saved",
        )

    if text in {"你好", "喂", "在吗", "你在吗", "小助手"}:
        return FastIntentResult(intent="wake", assistant_text="我在呢。", cached_audio_key="im_here")

    return None


def normalize_text(text: str) -> str:
    cleaned = re.sub(r"<\|[^|]+?\|>", "", text or "")
    cleaned = re.sub(r"[\s,，.。!！?？:：;；、]", "", cleaned)
    return cleaned.strip()


def _is_time_query(text: str) -> bool:
    return any(pattern in text for pattern in ("现在几点", "几点了", "当前时间", "现在时间"))


def _parse_reminder(text: str) -> tuple[int, str] | None:
    match = re.search(r"(\d+|一|两|二|三|四|五|六|七|八|九|十|十五|二十|半)(分钟|小时)后提醒我?(.*)", text)
    if match is None:
        return None
    amount = _parse_number(match.group(1))
    unit = match.group(2)
    thing = match.group(3).strip()
    minutes = amount * 60 if unit == "小时" else amount
    return max(1, minutes), thing


def _parse_pomodoro(text: str) -> int | None:
    if "番茄钟" not in text and "专注" not in text:
        return None
    match = re.search(r"(\d+|一|两|二|三|四|五|六|七|八|九|十|十五|二十|二十五|三十)分钟", text)
    if match is None:
        return 25
    return max(1, _parse_number(match.group(1)))


def _parse_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    mapping = {
        "一": 1,
        "两": 2,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
        "十五": 15,
        "二十": 20,
        "二十五": 25,
        "三十": 30,
        "半": 30,
    }
    return mapping.get(value, 1)
