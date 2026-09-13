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


_FORCE_LANG = (os.environ.get("MEGA_LANG") or "").strip().lower()
_FA = _FORCE_LANG == "fa" or (_FORCE_LANG != "en" and os.name != "nt")


def _say(text: str) -> None:
    """پیام خام (معمولاً خروجی pip)."""
    print(text, flush=True)


def T(fa: str, en: str) -> str:
    """پیام دوزبانه: ویندوز انگلیسی (فونت کنسول فارسی را نشان نمی‌دهد)، بقیه فارسی."""
    return fa if _FA else en


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


def ensure_pip(py: str) -> bool:
    """اگر مفسر pip ندارد، با ensurepip یا get-pip نصبش می‌کند."""
    try:
        r = subprocess.run([py, "-m", "pip", "--version"], capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            return True
    except Exception:  # noqa: BLE001
        pass

    for cmd in ([py, "-m", "ensurepip", "--upgrade", "--default-pip"],
                [py, "-m", "ensurepip", "--upgrade"]):
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except Exception:  # noqa: BLE001
            continue
        try:
            if subprocess.run([py, "-m", "pip", "--version"], capture_output=True,
                              text=True, timeout=180).returncode == 0:
                return True
        except Exception:  # noqa: BLE001
            pass

    try:
        import urllib.request
        gp = ROOT / ".get-pip.py"
        urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", gp)
        subprocess.run([py, str(gp)], capture_output=True, text=True, timeout=1200)
        gp.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    try:
        return subprocess.run([py, "-m", "pip", "--version"], capture_output=True,
                              text=True, timeout=180).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def ascii_requirements() -> Path | None:
    """یک کپی ASCII خالص از requirements.txt می‌سازد.

    چرا؟ pip فایل requirements را با کدپیج ویندوز (cp1252) می‌خواند و اگر در آن
    حرف فارسی باشد با UnicodeDecodeError می‌ترکد. پس همیشه نسخه‌ی ASCII می‌دهیم.
    """
    if not REQ.exists():
        return None
    if REQ.read_bytes().isascii():
        return REQ                                    # خودش ASCII است → دست نزن
    text = REQ.read_text(encoding="utf-8", errors="ignore")
    clean = "\n".join("".join(ch for ch in line if ord(ch) < 128).rstrip()
                      for line in text.splitlines())
    import tempfile
    fd, name = tempfile.mkstemp(prefix="mega-req-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="ascii", errors="ignore") as f:
        f.write(clean + "\n")
    return Path(name)


def install_python(py: str, packages: list[str] | None = None) -> bool:
    """نصب پکیج‌ها. اگر requirements.txt موجود باشد، همان نصب می‌شود."""
    if not ensure_pip(py):
        _say(T("⚠️  pip روی این پایتون نصب نشد (نه با ensurepip، نه با get-pip).",
               "[!] Could not install pip on this Python (tried ensurepip and get-pip)."))
        return False

    if packages:
        base = packages
    else:
        req_file = ascii_requirements()
        base = ["-r", str(req_file)] if req_file else list(dict.fromkeys(PY_DEPS.values()))

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


def install_tools(auto: bool = True) -> dict:
    """نصب خودکار ابزارهای جانبی (ffmpeg) با winget / apt / brew — بدون دخالت کاربر."""
    done: dict = {}
    if not missing_tools():
        return done
    if not auto or os.environ.get("MEGA_NO_AUTO_TOOLS"):
        return done

    cmd: list[str] | None = None
    if os.name == "nt":
        if shutil.which("winget"):
            cmd = ["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--silent",
                   "--accept-package-agreements", "--accept-source-agreements"]
    else:
        if shutil.which("apt-get") and hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd = ["apt-get", "install", "-y", "ffmpeg"]
        elif shutil.which("brew"):
            cmd = ["brew", "install", "ffmpeg"]
    if not cmd:
        return done

    _say(T("   نصب خودکار ffmpeg …", "   auto-installing ffmpeg ..."))
    try:
        r = subprocess.run(cmd, timeout=1800)
        done["ffmpeg"] = (r.returncode == 0 and not missing_tools())
    except Exception as e:  # noqa: BLE001
        _say(T(f"   ⚠️  نصب خودکار ابزارها انجام نشد: {e}", f"   [!] auto-install failed: {e}"))
        done["ffmpeg"] = False
    return done


def tool_hint_en(name: str) -> str:
    """همان راهنما به انگلیسی (برای کنسول ویندوز)."""
    if name == "ffmpeg":
        if os.name == "nt":
            return ("video/audio needs it. In an admin PowerShell run:  "
                    "winget install -e --id Gyan.FFmpeg   "
                    "(or download from https://www.gyan.dev/ffmpeg/builds/ and add its bin folder to PATH)")
        return "install:  sudo apt install ffmpeg   (or: brew install ffmpeg)"
    return ""


def ensure_all(py: str, install: bool = True, tools: bool = True) -> dict:
    """همهٔ پیش‌نیازها را بررسی (و در صورت اجازه) نصب می‌کند."""
    result: dict = {"python_ok": True, "installed": False, "missing_pkgs": [],
                    "missing_tools": [], "tools_installed": {}}



    missing = missing_python(py)
    if not missing:
        _say(T("📦 کتابخانه‌های پایتون: همه نصب‌اند ✅", "[OK] Python libraries: all installed"))
    else:
        _say(T("📦 کتابخانه‌های غایب: ", "Missing libraries: ") + ", ".join(missing))
        if install:
            _say(T("   در حال نصب … (بار اول چند دقیقه)", "   installing ... (first run takes a few minutes)"))
            ok = install_python(py)
            rest = missing_python(py)
            result["installed"] = ok and not rest
            result["missing_pkgs"] = rest
            _say(T("   ✅ نصب شد", "   [OK] installed") if not rest else T("   ⚠️  این‌ها نصب نشد: ", "   [!] failed: ") + ", ".join(rest))
        else:
            result["missing_pkgs"] = missing
            _say(T("   (بدون نصب — با --no-install اجرا شده)", "   (skipped: --no-install)"))

    tools = missing_tools()
    if tools and install and tools:
        result["tools_installed"] = install_tools(auto=True)
        tools = missing_tools()
    result["missing_tools"] = tools
    if not tools:
        _say(T("🛠  ابزارهای جانبی: ffmpeg نصب است ✅ (ویدیو/صدا آماده)", "[OK] ffmpeg installed (video/audio ready)"))
    else:
        for t in tools:
            _say(T(f"🛠  ابزار «{t}» نصب نیست — {tool_hint(t)}", f"[!] {t} is missing - {tool_hint_en(t)}"))

    result["python_ok"] = bool(py)
    return result


if __name__ == "__main__":
    r = ensure_all(sys.executable, install="--no-install" not in sys.argv)
    print(r)
