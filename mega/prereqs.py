# -*- coding: utf-8 -*-
"""
prereqs.py — بررسی و نصب پیش‌نیازهای برنامه (کتابخانه‌های pip + ابزارهای جانبی)

  * PY_DEPS : نگاشت «نام ماژول» → «نام پکیج pip»
  * missing_python(py)         → پکیج‌های نصب‌نشده
  * install_python(py, pkgs)   → نصب با pip (با تلاش دوباره از mirror ایرانی)
  * missing_tools()            → ابزارهای جانبی غایب (ffmpeg برای ویدیو/صدا)
  * ensure_all(py, install)    → همه‌چیز را یک‌جا بررسی/نصب می‌کند
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "requirements.txt"

# ماژولِ قابل import → نام پکیج در pip
PY_DEPS: dict[str, str] = {
    # هسته
    "fastapi": "fastapi",
    "uvicorn": "uvicorn[standard]",
    "httpx": "httpx",
    "multipart": "python-multipart",
    "dotenv": "python-dotenv",
    # رسانه
    "PIL": "pillow",
    "edge_tts": "edge-tts",
    "qrcode": "qrcode",
    # داده و سند
    "pandas": "pandas",
    "numpy": "numpy",
    "matplotlib": "matplotlib",
    "openpyxl": "openpyxl",
    "pypdf": "pypdf",
    "docx": "python-docx",
    # فارسی در تصویر/نمودار
    "arabic_reshaper": "arabic-reshaper",
    "bidi": "python-bidi",
    # وضعیت سیستم
    "psutil": "psutil",
}

# دستور pip اول (mirror ایرانی می‌تواند تحریم/کندی را دور بزند)
PIP_INDEXES = (
    "https://pypi.org/simple",
    "https://mirror-pypi.runflare.com/simple",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
)


def _say(text: str) -> None:
    print(text, flush=True)


def missing_python(py: str) -> list[str]:
    """پکیج‌های pip که در مفسر داده‌شده قابل import نیستند."""
    probe = (
        "import importlib.util as u\n"
        "mods = " + repr({m: p for m, p in PY_DEPS.items()}) + "\n"
        "print(','.join(pkg for mod, pkg in mods.items() if u.find_spec(mod) is None))\n"
    )
    try:
        r = subprocess.run([py, "-c", probe], capture_output=True, text=True, timeout=180)
        out = (r.stdout or "").strip()
        return [x for x in out.split(",") if x]
    except Exception:  # noqa: BLE001
        return []


def install_python(py: str, packages: list[str] | None = None) -> bool:
    """نصب پکیج‌ها. اگر requirements.txt موجود باشد، همان نصب می‌شود."""
    if packages:
        base = packages
    elif REQ.exists():
        base = ["-r", str(REQ)]
    else:
        base = list(dict.fromkeys(PY_DEPS.values()))

    quiet = "1" if os.environ.get("MEGA_NO_VENV") else None
    for i, index in enumerate(PIP_INDEXES, 1):
        cmd = [py, "-m", "pip", "install", "--upgrade", "--index-url", index] + base
        _say(f"   pip ({i}/{len(PIP_INDEXES)}): {index}")
        try:
            r = subprocess.run(cmd, timeout=1800)
        except Exception as e:  # noqa: BLE001
            _say(f"   ⚠️  {e}")
            continue
        if r.returncode == 0 and not missing_python(py):
            return True
    return not missing_python(py)


def _tool(name: str) -> bool:
    return shutil.which(name) is not None


def missing_tools() -> list[str]:
    """ابزارهای جانبی: ffmpeg برای ویدیو/صدا لازم است (بقیه اختیاری)."""
    missing = []
    if not (_tool("ffmpeg") and _tool("ffprobe")):
        missing.append("ffmpeg")
    return missing


def tool_hint(name: str) -> str:
    if name == "ffmpeg":
        if os.name == "nt":
            return ('ویدیو/صدا بدون آن کار نمی‌کند. در PowerShell (با Administrator) بزن:\n'
                    '        winget install -e --id Gyan.FFmpeg\n'
                    '     یا از https://www.gyan.dev/ffmpeg/builds/ دانلود کن و پوشه‌ی bin را به PATH اضافه کن.')
        return "نصب:  sudo apt install ffmpeg   (یا: brew install ffmpeg)"
    return ""


def ensure_all(py: str, install: bool = True) -> dict:
    """همهٔ پیش‌نیازها را بررسی (و در صورت اجازه) نصب می‌کند."""
    result: dict = {"python_ok": True, "installed": False, "missing_pkgs": [], "missing_tools": []}

    missing = missing_python(py)
    if not missing:
        _say("📦 کتابخانه‌های پایتون: همه نصب‌اند ✅")
    else:
        _say("📦 کتابخانه‌های غایب: " + ", ".join(missing))
        if install:
            _say("   در حال نصب … (بار اول چند دقیقه)")
            ok = install_python(py)
            rest = missing_python(py)
            result["installed"] = ok and not rest
            result["missing_pkgs"] = rest
            _say("   ✅ نصب شد" if not rest else "   ⚠️  این‌ها نصب نشد: " + ", ".join(rest))
        else:
            result["missing_pkgs"] = missing
            _say("   (بدون نصب — با --no-install اجرا شده)")

    tools = missing_tools()
    result["missing_tools"] = tools
    if not tools:
        _say("🛠  ابزارهای جانبی: ffmpeg نصب است ✅ (ویدیو/صدا آماده)")
    else:
        for t in tools:
            _say(f"🛠  ابزار «{t}» نصب نیست — {tool_hint(t)}")

    result["python_ok"] = bool(py)
    return result


if __name__ == "__main__":
    r = ensure_all(sys.executable, install="--no-install" not in sys.argv)
    print(r)
