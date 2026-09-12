#!/usr/bin/env python3
"""
اجراکننده‌ی محلی MEGA-AI — نصب خودکار + انتخاب پورت آزاد + باز کردن مرورگر.

روی لپ‌تاپ خودت (ویندوز/مک/لینوکس) فقط این را اجرا کن:

    python run_local.py

و اگر می‌خواهی از گوشی/تبلت هم به آن وصل شوی (همان شبکه‌ی وای‌فای):

    python run_local.py --lan

گزینه‌ها:
    --port 8000      پورت دلخواه (اگر مشغول بود، خودش پورت آزاد بعدی را برمی‌دارد)
    --host 127.0.0.1 آدرس اتصال (برای شبکه: 0.0.0.0)
    --no-browser     مرورگر باز نشود
    --no-install     نصب خودکار کتابخانه‌ها انجام نشود
    --check          فقط بررسی محیط (بدون اجرای سرور)
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQ = ROOT / "requirements.txt"
IS_WIN = os.name == "nt"
MIN_PY = (3, 10)

CORE_DEPS = {"fastapi": "fastapi", "uvicorn": "uvicorn", "httpx": "httpx",
             "multipart": "python-multipart", "PIL": "pillow"}
NICE_DEPS = {"pandas": "pandas", "matplotlib": "matplotlib", "openpyxl": "openpyxl",
             "pypdf": "pypdf", "docx": "python-docx", "psutil": "psutil",
             "arabic_reshaper": "arabic-reshaper", "bidi": "python-bidi/wrapper"}


def c(text: str, code: str = "") -> str:
    if IS_WIN and not os.environ.get("WT_SESSION"):
        return text
    codes = {"g": "32", "y": "33", "r": "31", "b": "36", "bold": "1"}
    return f"\033[{codes.get(code, '0')}m{text}\033[0m"


def say(msg: str) -> None:
    print(f"  {msg}", flush=True)


def have(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def venv_python() -> Path:
    d = ROOT / ".venv"
    return d / ("Scripts/python.exe" if IS_WIN else "bin/python")


def ensure_venv() -> str:
    """اگر داخل محیط مجازی نیستیم، `.venv` می‌سازد و مسیر پایتونِ آن را برمی‌گرداند."""
    if os.environ.get("MEGA_NO_VENV") or sys.prefix != sys.base_prefix:
        return sys.executable                        # همین حالا داخل محیط مجازی هستیم
    vp = venv_python()
    if not vp.exists():
        say(c("ساخت محیط مجازی (.venv) — یک‌بار برای همیشه …", "b"))
        try:
            # با --system-site-packages: کتابخانه‌های نصب‌شده‌ی سیستم هم دیده می‌شوند
            subprocess.run([sys.executable, "-m", "venv", "--system-site-packages",
                            str(ROOT / ".venv")], check=True)
        except Exception as e:  # noqa: BLE001
            say(c(f"ساخت venv نشد ({e}) — با پایتون سیستم ادامه می‌دهم.", "y"))
            os.environ["MEGA_NO_VENV"] = "1"
            return sys.executable
    return str(vp)


def deps_missing(py: str) -> list[str]:
    """پکیج‌های pip که در همان مفسر داده‌شده نصب نیستند (فهرست کامل: mega/prereqs.py)."""
    try:
        sys.path.insert(0, str(ROOT))
        from mega.prereqs import missing_python
        return missing_python(py)
    except Exception:  # noqa: BLE001 — نبودِ فایل نباید اجرا را متوقف کند
        probe = ("import importlib.util as u\n"
                 "mods = {'fastapi':'fastapi','uvicorn':'uvicorn','httpx':'httpx',"
                 "'multipart':'python-multipart','PIL':'pillow','pandas':'pandas',"
                 "'matplotlib':'matplotlib','openpyxl':'openpyxl','pypdf':'pypdf',"
                 "'docx':'python-docx','arabic_reshaper':'arabic-reshaper','bidi':'python-bidi'}\n"
                 "print(','.join(pkg for mod, pkg in mods.items() if u.find_spec(mod) is None))")
        try:
            r = subprocess.run([py, "-c", probe], capture_output=True, text=True, timeout=120)
            return [x for x in (r.stdout or "").strip().split(",") if x]
        except Exception:
            return []


def pip_install(py: str, packages: list[str] | None = None) -> bool:
    """نصب پکیج‌ها با pip — با چند mirror (پایتون‌پای اصلی و آینه‌های در دسترس از ایران)."""
    try:
        sys.path.insert(0, str(ROOT))
        from mega.prereqs import install_python
        return install_python(py, packages)
    except Exception:  # noqa: BLE001
        cmd = [py, "-m", "pip", "install", "--upgrade"] + (packages or ["-r", str(REQ)])
        try:
            return subprocess.run(cmd).returncode == 0
        except Exception:
            return False


def ensure_deps(py: str, install: bool = True) -> None:
    """همهٔ پیش‌نیازها: کتابخانه‌ها + ابزارهای جانبی (ffmpeg)."""
    try:
        sys.path.insert(0, str(ROOT))
        from mega.prereqs import ensure_all
        ensure_all(py, install=install)
        return
    except Exception:  # noqa: BLE001
        pass
    missing = deps_missing(py)
    if not missing:
        say(c("همه‌ی کتابخانه‌های لازم نصب‌اند ✅", "g"))
        return
    say(c("کتابخانه‌های لازم نیستند: " + ", ".join(missing), "y"))
    if install:
        pip_install(py, missing)
    else:
        say("با --no-install رد شدی؛ اگر چیزی کم بود: " + c(f"{py} -m pip install -r requirements.txt", "b"))


def check_tools() -> dict[str, bool]:
    tools = {"ffmpeg": "ساخت ویدیو/صدا", "ffprobe": "اطلاعات ویدیو", "git": "نصب مهارت از مخزن",
             "node": "بررسی کد جاوااسکریپت", "npm": "ساخت پروژه‌های وب"}
    out: dict[str, bool] = {}
    print()
    print(c("  ابزارهای سیستمی:", "bold"))
    for t, why in tools.items():
        ok = bool(shutil.which(t))
        out[t] = ok
        mark = c("✅", "g") if ok else c("—", "y")
        say(f"{mark} {t:9} {why}" + ("" if ok else c("   (نصب نیست — بخش وابسته به آن کار نمی‌کند)", "y")))
    if not out.get("ffmpeg"):
        hint = ("winget install Gyan.FFmpeg" if IS_WIN else
                "brew install ffmpeg" if platform.system() == "Darwin" else
                "sudo apt install ffmpeg")
        say(c(f"برای ویدیو: {hint}", "y"))
    return out


def free_port(preferred: int = 8000) -> int:
    for p in range(preferred, preferred + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    with socket.socket() as s:                       # هر پورت آزادی که سیستم بدهد
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def wait_up(port: int, host: str = "127.0.0.1", timeout: float = 60) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except OSError:
            time.sleep(0.6)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True, description="اجراکننده‌ی محلی MEGA-AI")
    ap.add_argument("--port", type=int, default=int(os.environ.get("MEGA_PORT") or os.environ.get("PORT") or 8000))
    ap.add_argument("--host", default="")
    ap.add_argument("--lan", action="store_true", help="در شبکه هم در دسترس باشد (گوشی/تبلت)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-install", action="store_true")
    ap.add_argument("--no-venv", action="store_true", help="بدون ساخت محیط مجازی (نصب در پایتون سیستم)")
    ap.add_argument("--check", action="store_true", help="فقط بررسی محیط")
    args = ap.parse_args()

    print()
    print(c("  ╔══════════════════════════════════════════╗", "bold"))
    print(c("  ║     MehranAiShabestar — هوش مصنوعی تو    ║", "bold"))
    print(c("  ╚══════════════════════════════════════════╝", "bold"))
    print()
    say(f"پایتون: {platform.python_version()} · سیستم: {platform.system()} {platform.release()}")

    if sys.version_info < MIN_PY:
        say(c(f"پایتون {MIN_PY[0]}.{MIN_PY[1]} یا بالاتر لازم است (فعلی: {platform.python_version()}).", "r"))
        return 2

    if args.no_venv:
        os.environ["MEGA_NO_VENV"] = "1"
    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")

    # ── محیط مجازی: بساز و اگر لازم بود خودمان را با آن دوباره اجرا کن
    py = ensure_venv()
    if Path(py) != Path(sys.executable):
        missing = deps_missing(py)
        if missing and not args.no_install:
            subprocess.run([py, "-m", "pip", "install", "--upgrade", "--quiet", "pip"],
                           capture_output=True, text=True)
            ensure_deps(py, install=True)
        elif missing:
            say(c("کتابخانه‌های لازم در .venv نیستند و --no-install داده شده.", "y"))
        # نصب‌های سنگین (اجرای سرور) داخل venv و در پروسه‌ی فرزند
        env = {**os.environ, "MEGA_NO_VENV": "1"}
        argv = [py, str(ROOT / "run_local.py"), "--port", str(args.port), "--host", host,
                "--no-install"]
        if args.no_browser:
            argv.append("--no-browser")
        if args.lan:
            argv.append("--lan")
        if args.check:
            argv.append("--check")
        return subprocess.call(argv, cwd=str(ROOT), env=env)

    # ── همین مفسر: بررسی کتابخانه‌ها
    ensure_deps(py, install=not args.no_install)

    # ── پورت آزاد (اگر مشغول بود، پورت دیگری)
    port = free_port(args.port)
    if port != args.port:
        say(c(f"پورت {args.port} مشغول بود؛ پورت {port} انتخاب شد.", "y"))

    check_tools()
    print()
    url = f"http://{'localhost' if not args.lan else lan_ip()}:{port}"
    say(c(f"پنل: {url}", "g"))
    if args.lan:
        say(c(f"از گوشی/تبلت هم: http://{lan_ip()}:{port}   (روی همان وای‌فای)", "b"))
    say("برای توقف: Ctrl+C")
    print()

    if args.check:
        say(c("بررسی کامل شد (سرور اجرا نشد).", "g"))
        return 0

    proc = subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=str(ROOT),
                            env={**os.environ, "MEGA_HOST": ("0.0.0.0" if args.lan else host),
                                 "MEGA_PORT": str(port)})
    if wait_up(port) and not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        proc.wait()
    except KeyboardInterrupt:
        say("خاموش می‌کنم…")
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        print("  خداحافظ 👋")
        raise SystemExit(0)
