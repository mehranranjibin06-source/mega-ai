# -*- coding: utf-8 -*-
"""🔄 آپدیت یک‌مرحله‌ای MehranAiShabestar — **مستقل** (از هر نسخه‌ای کار می‌کند).

در CMD داخل پوشهٔ برنامه:

    python update_self.py             # نسخهٔ تازه را می‌گیرد و نصب می‌کند
    python update_self.py --restart   # + برنامه را دوباره بالا می‌آورد (پورت ۸۰۰۰/۸۰۰۱)

هیچ کتابخانه‌ای لازم نیست (فقط پایتون خود ویندوز).
این فایل خودش را از پروژه جدا نگه می‌دارد تا وقتی نسخهٔ قدیمی نصب است هم کار کند.

🔒 دست‌نخورده می‌مانند:  .env · data/ · workspace/ · .venv/ · .git/
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIRRORS = [
    "https://codeload.github.com/mehranranjibin06-source/mega-ai/zip/refs/heads/main",
    "https://ghfast.top/https://github.com/mehranranjibin06-source/mega-ai/archive/refs/heads/main.zip",
    "https://ghproxy.net/https://github.com/mehranranjibin06-source/mega-ai/archive/refs/heads/main.zip",
    "https://gh-proxy.com/https://github.com/mehranranjibin06-source/mega-ai/archive/refs/heads/main.zip",
]
KEEP_DIRS = {"data", "workspace", ".venv", "venv", ".git", "__pycache__", ".pytest_cache", "logs", "assets_cache"}
KEEP_FILES = {".env", "mega.db", ".env.local"}
UA = {"User-Agent": "Mozilla/5.0 (MegaAI self-updater)"}


def say(msg: str) -> None:
    print("  " + msg, flush=True)


def current_version() -> str:
    f = ROOT / "mega" / "config.py"
    try:
        m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', f.read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except Exception:  # noqa: BLE001
        return "?"


def ver_of(path: Path) -> str:
    try:
        m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', (path / "mega" / "config.py").read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except Exception:  # noqa: BLE001
        return "?"


def download() -> tuple[bytes, str]:
    last = ""
    for url in MIRRORS:
        try:
            say(f"⬇️  {url.split('/')[2]} …")
            req = urllib.request.Request(url, headers=UA)
            data = urllib.request.urlopen(req, timeout=180).read()
            if len(data) > 300_000:
                return data, url
            last = f"{url} → فقط {len(data)} بایت"
        except Exception as e:  # noqa: BLE001
            last = f"{url} → {type(e).__name__}: {e}"
            say(f"   ⚠️ نشد: {type(e).__name__}")
    raise RuntimeError("دانلود ناموفق بود — " + last)


def extract(data: bytes) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="mega-up-"))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if not any(n.endswith("mega/config.py") for n in z.namelist()):
            raise RuntimeError("فایل دانلودشده معتبر نیست")
        for n in z.namelist():
            tgt = (tmp / n).resolve()
            if not str(tgt).startswith(str(tmp.resolve())):
                raise RuntimeError("آرشیو ناایمن")
        z.extractall(tmp)
    inner = [d for d in tmp.iterdir() if d.is_dir()]
    if len(inner) == 1 and (inner[0] / "mega").is_dir():
        return inner[0]
    return tmp


def copy_over(src: Path) -> list[str]:
    changed: list[str] = []
    for item in sorted(src.rglob("*")):
        rel = item.relative_to(src)
        if any(part in KEEP_DIRS for part in rel.parts) or item.name in KEEP_FILES or item.suffix == ".pyc":
            continue
        target = ROOT / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        new = item.read_bytes()
        if not target.is_file() or target.read_bytes() != new:
            target.write_bytes(new)
            changed.append(str(rel).replace("\\", "/"))
    return changed


def _listeners(ports=(8000, 8001)) -> list[int]:
    pids: list[int] = []
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                             timeout=25).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[3] == "LISTENING":
                port = parts[1].rsplit(":", 1)[-1]
                if port in {str(p) for p in ports}:
                    try:
                        pids.append(int(parts[4]))
                    except ValueError:
                        pass
    except Exception:  # noqa: BLE001
        pass
    return sorted(set(pids))


def restart() -> None:
    pids = _listeners()
    for pid in pids:
        say(f"⏹ بستن اجرای قبلی (PID {pid})")
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    if pids:
        time.sleep(3)
    say("🚀 بالا آوردن برنامه…")
    creation = 0x00000008 | 0x00000200          # DETACHED_PROCESS | NEW_PROCESS_GROUP
    try:
        subprocess.Popen([sys.executable, "start_vps.py"], cwd=str(ROOT), close_fds=True,
                         creationflags=creation)
    except Exception:  # noqa: BLE001
        subprocess.Popen(["python", "start_vps.py"], cwd=str(ROOT), close_fds=True)
    say("✅ برنامه دوباره روشن شد — ۱۵ ثانیه صبر کن، بعد صفحه را باز کن (پورت ۸۰۰۰)")


def main() -> int:
    before = current_version()
    print("=" * 64)
    print(f"  MehranAiShabestar — آپدیت خودکار     (نسخهٔ فعلی: v{before})")
    print("=" * 64)
    try:
        data, url = download()
    except Exception as e:  # noqa: BLE001
        print("\n  ❌ " + str(e))
        print("  چند لحظه بعد دوباره امتحان کن (اینترنت قطع و وصل می‌شود).")
        return 1
    try:
        box = extract(data)
    except Exception as e:  # noqa: BLE001
        print("\n  ❌ " + str(e))
        return 1

    after = ver_of(box)
    changed = copy_over(box)
    shutil.rmtree(box.parent if box.parent.name.startswith("mega-up-") else box, ignore_errors=True)

    print()
    print(f"  ✅ نسخه: v{before} → v{after}      ({len(changed)} فایل به‌روز شد)")
    for f in changed[:40]:
        print("     -", f)
    print("  🔒 دست‌نخورده: .env · data · workspace · .venv")
    if not changed:
        print("  ℹ️  چیز تازه‌ای نبود؛ همان نسخهٔ آخر را داری.")
    print("\n  ➡️  برای فعال شدن، در CMD این را بزن:  python start_vps.py")
    print("      یا همین حالا خودکار:  python update_self.py --restart")

    if "--restart" in sys.argv:
        print()
        restart()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
