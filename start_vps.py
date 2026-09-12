# -*- coding: utf-8 -*-
"""
start_vps.py — راه‌اندازی «ابرهوش» روی سرور ویندوزی خودت (رابط فارسی)

کارهایی که خودش انجام می‌دهد:
  ۱) بررسی نسخه‌ی پایتون
  ۲) گرفتن رمز (بار اول) و ذخیره در .env
  ۳) نصب/بررسی کتابخانه‌ها در محیط مجازی جدا (.venv) — به ربات معامله‌گر دست نمی‌زند
  ۴) باز کردن پورت در فایروال ویندوز
  ۵) اجرای برنامه و نمایش آدرس برای گوشی

اجرا:  روی start_vps.bat دوبار کلیک کن (یا: python start_vps.py)
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
DEFAULT_PORT = 8000


def say(text: str = "") -> None:
    print(text, flush=True)


def is_windows() -> bool:
    return os.name == "nt"


def is_admin() -> bool:
    if not is_windows():
        return False
    try:
        import ctypes  # type: ignore
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def read_password() -> str:
    pw = (os.environ.get("MEGA_PASSWORD") or "").strip()
    if pw:
        return pw
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("MEGA_PASSWORD="):
                return line.split("=", 1)[1].strip()
    return ""


def ask_password() -> str:
    """رمز را از کاربر می‌گیرد و در .env ذخیره می‌کند."""
    say("🔐 یک رمز برای برنامه انتخاب کن (فقط خودت بدانی).")
    say("   این رمز جلوی دسترسی غریبه‌ها به برنامه روی سرورت را می‌گیرد.")
    say("   نکته: وقتی تایپ می‌کنی حروف نمایش داده نمی‌شوند — طبیعی است، فقط تایپ کن و Enter بزن.")
    say("")
    try:
        pw = input("   رمز دلخواه: ").strip()
    except (EOFError, KeyboardInterrupt):
        say("")
        say("❌ رمزی وارد نشد. دوباره اجرا کن و یک رمز بزن.")
        sys.exit(1)
    if not pw:
        say("❌ رمز خالی بود. دوباره اجرا کن و یک رمز بزن.")
        sys.exit(1)
    try:
        with ENV_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\nMEGA_PASSWORD={pw}\n")
    except Exception as e:  # noqa: BLE001
        say(f"⚠️  ذخیره‌ی رمز در .env ممکن نشد ({e}) — فقط برای همین اجرا استفاده می‌شود.")
    os.environ["MEGA_PASSWORD"] = pw
    say("✅ رمز ذخیره شد.")
    say("")
    return pw


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def choose_port(preferred: int) -> int:
    for p in range(preferred, preferred + 40):
        if not port_in_use(p):
            return p
    return preferred


def open_firewall(port: int) -> bool:
    """پورت را در فایروال ویندوز باز می‌کند (نیاز به Administrator)."""
    if not is_windows():
        return True
    name = f"MEGA-AI {port}"
    try:
        shown = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
                               capture_output=True, text=True)
        if shown.returncode == 0:
            return True
        r = subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={name}",
                            "dir=in", "action=allow", "protocol=TCP", f"localport={port}"],
                           capture_output=True, text=True)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        if not ip.startswith(("127.", "169.254.")):
            return ip
    except Exception:  # noqa: BLE001
        pass
    return ""


def main() -> int:
    say("=" * 60)
    say("   ابرهوش — راه‌اندازی روی سرور خودت (کنار ربات معامله‌گر)")
    say("=" * 60)
    say("")

    # ۱) پایتون
    v = sys.version_info
    ver = ".".join(str(x) for x in v[:3])
    if v >= (3, 10):
        say(f"🐍 پایتون: {ver}  ✅")
    else:
        say(f"🐍 پایتون: {ver}  ❌  (نسخه‌ی ۳.۱۰ یا بالاتر لازم است)")
        say("   از https://www.python.org/downloads/ نسخه‌ی جدید را نصب کن.")
        return 1
    say("")

    # ۲) رمز
    pw = read_password()
    if pw:
        say("🔐 رمز فعال است ✅")
        say("")
    else:
        pw = ask_password()
    os.environ["MEGA_PASSWORD"] = pw

    # ۳) کتابخانه‌ها (محیط مجازی جدا؛ ربات معامله‌گر دست نمی‌خورد)
    say("📦 بررسی و نصب کتابخانه‌ها … (بار اول چند دقیقه)")
    try:
        sys.path.insert(0, str(ROOT))
        from run_local import ensure_deps, ensure_venv  # type: ignore
        py = ensure_venv()
        ensure_deps(py, install=True)
    except Exception as e:  # noqa: BLE001
        say(f"⚠️  آماده‌سازی خودکار ناتمام ماند ({e})")
        say("   دستی اجرا کن:  python -m pip install -r requirements.txt")
        py = sys.executable
    say("")

    # ۴) پورت + فایروال
    port = choose_port(int(os.environ.get("MEGA_PORT") or DEFAULT_PORT))
    if port != DEFAULT_PORT:
        say(f"ℹ️  پورت {DEFAULT_PORT} مشغول بود → پورت {port} انتخاب شد.")
    say(f"🚪 پورت: {port}")
    if is_windows():
        if not is_admin():
            say("ℹ️  این پنجره Administrator نیست؛ اگر پورت بسته باشد، برنامه فقط از خود سرور باز می‌شود.")
        if open_firewall(port):
            say("✅ پورت در فایروال ویندوز باز است.")
        else:
            say("⚠️  بازکردن پورت در فایروال انجام نشد. برای بازکردن دستی، این را در CMD (با Administrator) بزن:")
            say(f'   netsh advfirewall firewall add rule name="MEGA-AI {port}" dir=in action=allow protocol=TCP localport={port}')
    say("")

    # ۵) اجرا
    ip = lan_ip()
    say("=" * 60)
    say("  🚀 برنامه اجرا شد!  این پنجره را باز بگذار.")
    if ip:
        say(f"  📱 از گوشی (با همان وای‌فای/شبکه):   http://{ip}:{port}")
        say(f"  🖥  از خود سرور:                      http://localhost:{port}")
    else:
        say(f"  آدرس: http://<آی‌پی-سرورت>:{port}")
    say("  🔑 ورود: نام کاربری هرچه باشد (مثلاً 1) — فقط رمزِ خودت")
    say("  ⏹  برای بستن: این پنجره را ببند یا Ctrl+C")
    say("=" * 60)
    say("")

    env = {**os.environ, "MEGA_HOST": "0.0.0.0", "MEGA_PORT": str(port), "MEGA_NO_VENV": "1"}
    try:
        return subprocess.run([py, str(ROOT / "server.py")], cwd=str(ROOT), env=env).returncode
    except KeyboardInterrupt:
        say("\n⏹  بسته شد.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
