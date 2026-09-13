# -*- coding: utf-8 -*-
"""
free_ai.py — تلاش برای گرفتن پاسخ «واقعی» از سرویس‌های رایگان و بدون کلید.

هدف: کاربر بدون هیچ API Key هم جواب واقعی بگیرد.
اگر همه‌ی سرویس‌ها جواب ندادند، None برمی‌گرداند تا برنامه به «مدل نمایشی» برگردد.

خاموش‌کردن:   set MEGA_FREE_AI=0
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (MehranAiShabestar)"}
_TIMEOUT = float(os.environ.get("MEGA_FREE_AI_TIMEOUT") or 25)
_STATE = {"dead_until": 0.0, "last_error": ""}

# پاسخ‌هایی که «جواب واقعی» نیستند
_BAD_MARKERS = (
    "reached its budget", "too many requests", "rate limit", "quota", "unauthorized",
    "internal server error", "502 bad gateway", "nginx", "cloudflare",
)


def enabled() -> bool:
    return (os.environ.get("MEGA_FREE_AI") or "1").strip().lower() not in {"0", "false", "no"}


def _get(url: str, timeout: float | None = None) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT) as r:
        return r.read()


def _post(url: str, body: dict, timeout: float | None = None) -> bytes:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT) as r:
        return r.read()


def _clean(text: str) -> str | None:
    """پاسخ را بررسی می‌کند: اگر خطا/خالی بود None."""
    if not text:
        return None
    t = text.strip()
    if len(t) < 2:
        return None
    low = t.lower()
    if any(b in low for b in _BAD_MARKERS):
        return None
    if t.startswith("{") and '"error"' in low:
        return None
    return t


def _plain_prompt(messages: list[dict]) -> str:
    """آخرین پیام کاربر (به‌همراه کمی زمینه) برای سرویس‌های ساده."""
    parts = []
    for m in messages[-4:]:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            parts.append(f"[تنظیمات] {content[:600]}")
        elif role == "user":
            parts.append(content)
        elif role == "assistant":
            parts.append(f"[پاسخ قبلی] {content[:400]}")
    return "\n\n".join(parts)[-4000:] or "سلام"


def chat(messages: list[dict], timeout: float | None = None) -> str | None:
    """پاسخ واقعی از سرویس رایگان. اگر نشد → None"""
    if not enabled():
        return None
    if time.time() < _STATE["dead_until"]:
        return None                                  # تازه شکست خورده؛ معطل نکن

    prompt = _plain_prompt(messages)

    # ۱) pollinations — سازگار با OpenAI
    try:
        raw = _post("https://text.pollinations.ai/openai",
                    {"model": "openai", "messages": messages[-8:]})
        data = json.loads(raw.decode("utf-8", "replace"))
        txt = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        got = _clean(txt)
        if got:
            return got
    except Exception as e:  # noqa: BLE001
        _STATE["last_error"] = f"post: {type(e).__name__}"

    # ۲) pollinations — GET ساده
    for model in ("openai", "mistral"):
        try:
            url = ("https://text.pollinations.ai/" + urllib.parse.quote(prompt[:1800])
                   + f"?model={model}")
            got = _clean(_get(url).decode("utf-8", "replace"))
            if got:
                return got
        except Exception as e:  # noqa: BLE001
            _STATE["last_error"] = f"get-{model}: {type(e).__name__}"

    _STATE["dead_until"] = time.time() + 60          # ۶۰ ثانیه دیگر امتحان نکن
    return None


def image(prompt: str, width: int = 1024, height: int = 1024,
          timeout: float | None = None) -> bytes | None:
    """ساخت تصویر واقعی بدون کلید (pollinations). اگر نشد → None"""
    if not enabled():
        return None
    try:
        url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:900])
               + f"?width={int(width)}&height={int(height)}&nologo=true"
               + f"&seed={int(time.time()) % 99999}")
        blob = _get(url, timeout=timeout or 90)
        if blob[:3] == b"\xff\xd8\xff" or blob[:8] == b"\x89PNG\r\n\x1a\n":
            return blob
    except Exception as e:  # noqa: BLE001
        _STATE["last_error"] = f"image: {type(e).__name__}"
    return None


def status() -> dict:
    return {"enabled": enabled(), "cooling_down": time.time() < _STATE["dead_until"],
            "last_error": _STATE["last_error"]}


if __name__ == "__main__":
    print(json.dumps(status(), ensure_ascii=False))
    print(chat([{"role": "user", "content": "یک جمله کوتاه فارسی بگو"}]) or "— بدون پاسخ —")
