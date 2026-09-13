# -*- coding: utf-8 -*-
"""
local_llm.py — هوش مصنوعیِ «خودِ همین سرور» (بدون کلید، بدون اینترنت).

اگر روی سرور یکی از این‌ها نصب و روشن باشد، برنامه خودش پیدایش می‌کند و از
همان استفاده می‌کند — یعنی مدل واقعاً روی کامپیوتر خودت اجرا می‌شود:

  * Ollama            → http://127.0.0.1:11434   (پیشنهاد ما)
  * LM Studio         → http://127.0.0.1:1234
  * llama.cpp server  → http://127.0.0.1:8080
  * Jan / KoboldCpp   → http://127.0.0.1:1337 , :5001

نصب سریع Ollama در ویندوز (PowerShell با Administrator):
    winget install -e --id Ollama.Ollama
    ollama pull qwen2.5:1.5b        (یک‌بار؛ ~۱ گیگابایت)

خاموش‌کردن تشخیص خودکار:   set MEGA_NO_LOCAL=1
"""
from __future__ import annotations

import json
import os
import urllib.request

TIMEOUT = float(os.environ.get("MEGA_LOCAL_TIMEOUT") or 2.0)

# (نام, آدرس پایه, مسیر فهرست مدل‌ها, کلید مدل‌ها در پاسخ)
CANDIDATES = (
    ("Ollama", "http://127.0.0.1:11434", "/api/tags", "models", "name"),
    ("LM Studio", "http://127.0.0.1:1234", "/v1/models", "data", "id"),
    ("llama.cpp", "http://127.0.0.1:8080", "/v1/models", "data", "id"),
    ("Jan", "http://127.0.0.1:1337", "/v1/models", "data", "id"),
    ("KoboldCpp", "http://127.0.0.1:5001", "/v1/models", "data", "id"),
)


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "MehranAiShabestar"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _probe(base: str, path: str, keysrc: str, keyname: str) -> list[str]:
    data = _get(base.rstrip("/") + path)
    items = data.get(keysrc) or []
    return [m.get(keyname) for m in items if isinstance(m, dict) and m.get(keyname)]


def detect() -> dict | None:
    """اگر هوش محلی پیدا شد، آدرس و مدل‌هایش را برمی‌گرداند.

    MEGA_LOCAL_URL = آدرس هوشی که روی کامپیوتر دیگری است (مثلاً کامپیوتر خودت
    که با تونل به سرور وصل شده). مثال:  set MEGA_LOCAL_URL=http://127.0.0.1:11434
    """
    if (os.environ.get("MEGA_NO_LOCAL") or "").strip() in {"1", "true", "yes"}:
        return None

    remote = (os.environ.get("MEGA_LOCAL_URL") or os.environ.get("OLLAMA_HOST") or "").strip()
    if remote:
        if not remote.startswith("http"):
            remote = "http://" + remote
        for path, keysrc, keyname in (("/api/tags", "models", "name"), ("/v1/models", "data", "id")):
            try:
                models = _probe(remote, path, keysrc, keyname)
                if models:
                    api = remote.rstrip("/") + ("/v1" if path.startswith("/api") else "")
                    return {"kind": "Remote " + remote.split("//")[-1], "base_url": api,
                            "models": models[:20]}
            except Exception:  # noqa: BLE001
                continue

    for name, base, path, keysrc, keyname in CANDIDATES:
        try:
            data = _get(base + path)
            items = data.get(keysrc) or []
            models = [m.get(keyname) for m in items if isinstance(m, dict) and m.get(keyname)]
            if models:
                api = base + ("/v1" if path.startswith("/api") else "")
                return {"kind": name, "base_url": api, "models": models[:20]}
        except Exception:  # noqa: BLE001
            continue
    return None


def activate(found: dict) -> None:
    """هوش محلی را به‌عنوان یک پرووایدر آماده (بدون کلید) ثبت می‌کند."""
    from .config import PROVIDERS, Provider

    p = Provider(
        "local",
        f"🧠 {found['kind']} — هوش روی سرور خودت (بدون کلید)",
        "openai",
        found["base_url"],
        "LOCAL_LLM_KEY",
        found["models"],
        "",
    )
    p.key_override = "local"          # بدون کلید کار می‌کند
    PROVIDERS["local"] = p
    try:
        from .config import SETTINGS
        if hasattr(SETTINGS, "model") and not os.environ.get("MEGA_MODEL"):
            SETTINGS.model = found["models"][0]      # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def status() -> dict:
    found = detect()
    return {"found": bool(found), "kind": (found or {}).get("kind", ""),
            "models": (found or {}).get("models", [])[:5]}


# ── کمکی برای اسکریپت راه‌اندازی ───────────────────────────────────────
def ollama_installed() -> bool:
    import shutil
    return bool(shutil.which("ollama"))


if __name__ == "__main__":
    print(json.dumps(status(), ensure_ascii=False, indent=2))
