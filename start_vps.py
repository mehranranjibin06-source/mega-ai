# -*- coding: utf-8 -*-
"""
start_vps.py — راه‌اندازی MehranAiShabestar روی سرور ویندوزی خودت.

کارهایی که خودش انجام می‌دهد:
  ۱) بررسی نسخه‌ی پایتون
  ۲) گرفتن رمز (بار اول) و ذخیره در .env
  ۳) نصب/بررسی کتابخانه‌ها در محیط مجازی جدا (.venv) — به ربات معامله‌گر دست نمی‌زند
  ۴) باز کردن پورت در فایروال ویندوز
  ۵) اجرای برنامه و نمایش آدرس برای گوشی

نکته‌ی زبان: در کنسول ویندوز پیام‌ها انگلیسی چاپ می‌شوند (چون فونت کنسول حروف فارسی
را نشان نمی‌دهد و به‌شکل مربع درمی‌آید). برای فارسی اجباری:  set MEGA_LANG=fa
پنل وب همیشه فارسی است.
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

# ── زبان کنسول ────────────────────────────────────────────────────────
FORCE = (os.environ.get("MEGA_LANG") or "").strip().lower()
USE_FA = FORCE == "fa" or (FORCE != "en" and os.name != "nt")


def _utf8_console() -> None:
    """تلاش برای UTF-8 کردن کنسول ویندوز (برای وقتی MEGA_LANG=fa می‌دهی)."""
    if os.name == "nt":
        try:
            subprocess.run("chcp 65001", shell=True, capture_output=True)
        except Exception:  # noqa: BLE001
            pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def say(fa: str = "", en: str = "") -> None:
    """پیام دوزبانه: در ویندوز انگلیسی، در لینوکس/مک فارسی."""
    text = fa if USE_FA else (en or fa)
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
    say("🔐 یک رمز برای برنامه انتخاب کن (فقط خودت بدانی).",
        "🔐 Choose a password for the app (keep it private).")
    say("   این رمز جلوی دسترسی غریبه‌ها به برنامه روی سرورت را می‌گیرد.",
        "   It stops strangers from opening your app on this server.")
    say("   وقتی تایپ می‌کنی حروف نمایش داده نمی‌شوند — طبیعی است.",
        "   Nothing appears while you type - that is normal.")
    say("")
    try:
        pw = input("   Password: ").strip()
    except (EOFError, KeyboardInterrupt):
        say("", "")
        say("❌ رمزی وارد نشد. دوباره اجرا کن.", "❌ No password given. Run it again.")
        sys.exit(1)
    if not pw:
        say("❌ رمز خالی بود. دوباره اجرا کن.", "❌ Empty password. Run it again.")
        sys.exit(1)
    try:
        with ENV_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\nMEGA_PASSWORD={pw}\n")
    except Exception as e:  # noqa: BLE001
        say(f"⚠️  ذخیره‌ی رمز در .env ممکن نشد ({e}).", f"⚠️  Could not save the password to .env ({e}).")
    os.environ["MEGA_PASSWORD"] = pw
    say("✅ رمز ذخیره شد.", "✅ Password saved.")
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
    _utf8_console()
    say("=" * 62, "=" * 62)
    say("   MehranAiShabestar — راه‌اندازی روی سرور خودت",
        "   MehranAiShabestar - setup on your own server")
    say("=" * 62, "=" * 62)
    say("")

    # ۱) پایتون
    v = sys.version_info
    ver = ".".join(str(x) for x in v[:3])
    if v >= (3, 10):
        say(f"🐍 پایتون: {ver}  ✅", f"[OK] Python {ver}")
    else:
        say(f"🐍 پایتون: {ver}  ❌ (نسخه‌ی ۳.۱۰ یا بالاتر لازم است)",
            f"Python {ver} is too old - 3.10 or newer is required")
        say("   از https://www.python.org/downloads/ نصب کن.",
            "   Install it from https://www.python.org/downloads/")
        return 1
    say("")

    # ۲) رمز
    pw = read_password()
    if pw:
        say("🔐 رمز فعال است ✅", "[OK] Password is set")
        say("")
    else:
        pw = ask_password()
    os.environ["MEGA_PASSWORD"] = pw

    # ۳) کتابخانه‌ها (محیط مجازی جدا؛ ربات معامله‌گر دست نمی‌خورد)
    say("📦 بررسی و نصب کتابخانه‌ها … (بار اول چند دقیقه)",
        "Installing libraries ... (first run takes a few minutes)")
    try:
        sys.path.insert(0, str(ROOT))
        from run_local import ensure_deps, ensure_venv  # type: ignore
        py = ensure_venv()
        ensure_deps(py, install=True)
    except Exception as e:  # noqa: BLE001
        say(f"⚠️  آماده‌سازی خودکار ناتمام ماند ({e})",
            f"Automatic setup did not finish ({e})")
        say("   دستی: python -m pip install -r requirements.txt",
            "   Manual: python -m pip install -r requirements.txt")
        py = sys.executable
    say("")

    # ۴) پورت + فایروال
    wanted = int(os.environ.get("MEGA_PORT") or os.environ.get("PORT") or DEFAULT_PORT)
    port = choose_port(wanted)
    if port != wanted:
        say(f"ℹ️  پورت {wanted} مشغول بود → پورت {port} انتخاب شد.",
            f"[i] Port {wanted} was busy -> using port {port}")
    say(f"🚪 پورت: {port}", f"Port: {port}")
    if is_windows():
        if not is_admin():
            say("ℹ️  این پنجره Administrator نیست؛ پورت ممکن است بسته بماند.",
                "[i] This window is not Administrator; the port may stay closed.")
        if open_firewall(port):
            say("✅ پورت در فایروال باز است.", "[OK] Firewall port is open.")
        else:
            say("⚠️  بازکردن فایروال انجام نشد. دستی (CMD با Administrator):",
                "[!] Could not open the firewall. Run this in an admin CMD:")
            say(f'   netsh advfirewall firewall add rule name="MEGA-AI {port}" dir=in action=allow protocol=TCP localport={port}',
                f'   netsh advfirewall firewall add rule name="MEGA-AI {port}" dir=in action=allow protocol=TCP localport={port}')
    say("")

    # ۵) اجرا
    ip = lan_ip()
    say("=" * 62, "=" * 62)
    say("  🚀 برنامه اجرا شد! این پنجره را باز بگذار.",
        "  [RUNNING] Keep this window open!")
    if ip:
        say(f"  📱 از گوشی:  http://{ip}:{port}", f"  Phone:  http://{ip}:{port}")
        say(f"  🖥  از خود سرور:  http://localhost:{port}", f"  Server: http://localhost:{port}")
    else:
        say(f"  آدرس:  http://<server-ip>:{port}", f"  URL: http://<server-ip>:{port}")
    say("  🔑 ورود: نام کاربری هرچه باشد (مثلاً 1) — فقط رمز خودت",
        "  Login: any username (e.g. 1) + YOUR password")
    say("  ⏹  بستن: این پنجره را ببند یا Ctrl+C", "  Stop: close this window or Ctrl+C")
    say("=" * 62, "=" * 62)
    say("")

    env = {**os.environ, "MEGA_HOST": "0.0.0.0", "MEGA_PORT": str(port),
           "PORT": str(port), "MEGA_NO_VENV": "1"}
    try:
        return subprocess.run([py, str(ROOT / "server.py")], cwd=str(ROOT), env=env).returncode
    except KeyboardInterrupt:
        say("\n⏹  بسته شد.", "\n[stopped]")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
