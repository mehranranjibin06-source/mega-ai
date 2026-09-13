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
# دو گروه: «هسته» (برای بالا آمدن برنامه لازم است) و «سنگین/اختیاری»
# (اکسل، نمودار، PDF). این تقسیم برای نت‌های ضعیف حیاتی است: اول هسته‌ی کوچک
# نصب می‌شود تا برنامه بالا بیاید، بعد فایل‌های بزرگ در پس‌زمینه دانلود می‌شوند.
CORE_DEPS: dict[str, str] = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn[standard]",
    "httpx": "httpx",
    "multipart": "python-multipart",
    "dotenv": "python-dotenv",
    "PIL": "pillow",
    "edge_tts": "edge-tts",
    "qrcode": "qrcode",
    "arabic_reshaper": "arabic-reshaper",
    "bidi": "python-bidi",
    "psutil": "psutil",
}

EXTRA_DEPS: dict[str, str] = {
    "pandas": "pandas",
    "numpy": "numpy",
    "matplotlib": "matplotlib",
    "openpyxl": "openpyxl",
    "pypdf": "pypdf",
    "docx": "python-docx",
}

PY_DEPS: dict[str, str] = {**CORE_DEPS, **EXTRA_DEPS}

# پرچم‌های pip برای اینترنتِ قطع‌وصل: تلاش بیشتر + مهلت بلندتر + فقط فایل آماده
PIP_FLAGS = ("--retries", "20", "--timeout", "60", "--prefer-binary")

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


def missing_python(py: str, which: str = "all") -> list[str]:
    """پکیج‌های نصب‌نشده. which = all | core | extra"""
    table = {"all": PY_DEPS, "core": CORE_DEPS, "extra": EXTRA_DEPS}.get(which, PY_DEPS)
    probe = (
        "import importlib.util as u\n"
        "mods = " + repr(dict(table)) + "\n"
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


def _pip_once(py: str, args: list[str], index: str, label: str) -> bool:
    cmd = [py, "-m", "pip", "install", "--upgrade", *PIP_FLAGS,
           "--index-url", index, *args]
    _say(f"   pip {label}: {index}")
    try:
        return subprocess.run(cmd, timeout=3600).returncode == 0
    except Exception as e:  # noqa: BLE001
        _say(f"   [!] {e}")
        return False


def install_group(py: str, args: list[str], rounds: int = 2) -> bool:
    """نصب با چند دور تلاش — pip هر دانلود نیمه‌کاره را در کش نگه می‌دارد و
    دفعه‌ی بعد از همان‌جا ادامه می‌دهد؛ پس نت قطع‌وصل‌دار هم آخرش تمام می‌شود."""
    done = False
    for rnd in range(1, rounds + 1):
        if rnd > 1:
            _say(T(f"   ⟳ دور {rnd} — ادامه از محل قطع (فایل‌های دانلودشده دوباره دانلود نمی‌شوند)",
                   f"   [round {rnd}] retrying - finished downloads stay in cache"))
        for i, index in enumerate(PIP_INDEXES, 1):
            if _pip_once(py, args, index, f"({i}/{len(PIP_INDEXES)})"):
                return True
    return done


def install_python(py: str, packages: list[str] | None = None, extras: bool = True) -> bool:
    """نصب مرحله‌ای: اول هسته (کوچک) تا برنامه بالا بیاید، بعد کتابخانه‌های سنگین."""
    if not ensure_pip(py):
        _say(T("⚠️  pip روی این پایتون نصب نشد (نه با ensurepip، نه با get-pip).",
               "[!] Could not install pip on this Python (tried ensurepip and get-pip)."))
        return False

    if packages:
        return install_group(py, packages)

    req_file = ascii_requirements()

    # مرحله ۱ — هسته: کوچک (چند مگابایت) و سریع
    if missing_python(py, "core"):
        _say(T(f"   مرحله ۱ از ۲ — هسته ({len(CORE_DEPS)} پکیج کوچک، چند مگابایت)",
               f"   step 1 of 2 - core ({len(CORE_DEPS)} small packages)"))
        install_group(py, ["--upgrade"] + list(dict.fromkeys(CORE_DEPS.values())), rounds=2)
    core_ok = not missing_python(py, "core")

    # مرحله ۲ — سنگین‌ها (اکسل/نمودار/PDF)؛ نبودنشان برنامه را زمین نمی‌زند
    if extras and missing_python(py, "extra"):
        if not core_ok:
            _say(T("   ⚠️  هسته کامل نشد؛ کل فهرست را یک‌بار امتحان می‌کنم.",
                   "   [!] core is incomplete - trying the full list once."))
            if req_file:
                install_group(py, ["-r", str(req_file)], rounds=1)
            core_ok = not missing_python(py, "core")
        rest = missing_python(py, "extra")
        if rest:
            _say(T("   مرحله ۲ از ۲ — کتابخانه‌های سنگین ~۴۰ مگابایت (اکسل، نمودار، PDF)",
                   "   step 2 of 2 - heavy libraries ~40 MB (Excel, charts, PDF)"))
            _say(T("   با نت ضعیف ممکن است نیمه‌کاره بماند؛ بار بعد خودش ادامه می‌دهد.",
                   "   on a weak connection this may stay partial; the next run resumes."))
            if req_file:
                install_group(py, ["-r", str(req_file)], rounds=1)
    return core_ok


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



    missing = missing_python(py, "core")
    heavy = missing_python(py, "extra")
    if not missing and not heavy:
        _say(T("📦 کتابخانه‌های پایتون: همه نصب‌اند ✅", "[OK] Python libraries: all installed"))
    else:
        if missing:
            _say(T("📦 کتابخانه‌های اصلی غایب: ", "Missing core libraries: ") + ", ".join(missing))
        if heavy:
            _say(T("🧩 کتابخانه‌های سنگین (اکسل/نمودار) غایب: ", "Missing heavy extras: ") + ", ".join(heavy))
        if install:
            _say(T("   در حال نصب … (بار اول چند دقیقه)", "   installing ... (first run takes a few minutes)"))
            ok = install_python(py)
            rest = missing_python(py, "core")
            rest_heavy = missing_python(py, "extra")
            result["installed"] = ok and not rest
            result["missing_pkgs"] = rest
            result["missing_extras"] = rest_heavy
            if not rest and not rest_heavy:
                _say(T("   ✅ نصب شد", "   [OK] installed"))
            elif not rest:
                _say(T("   ✅ هسته نصب شد (سنگین‌ها نیمه‌کاره — بار بعد ادامه می‌دهد): ",
                       "   [OK] core installed (heavy extras incomplete - next run continues): ")
                     + ", ".join(rest_heavy))
            else:
                _say(T("   ⚠️  این‌ها نصب نشد: ", "   [!] failed: ") + ", ".join(rest))
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
