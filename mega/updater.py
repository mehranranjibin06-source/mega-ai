# -*- coding: utf-8 -*-
"""🔄 آپدیت خودکار برنامه از گیت‌هاب + ری‌استارت امن.

کاربر روی گوشی دکمهٔ «آپدیت» را می‌زند؛ سرور نسخهٔ تازه را از GitHub (و آینه‌های
داخل ایران) می‌گیرد، فایل‌ها را جای‌گزین می‌کند و بعد فقط یک ری‌استارت کوچک لازم است.

هیچ‌وقت این‌ها دست نمی‌خورند:  .env ، data/ ، workspace/ ، .venv/ ، .git/
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
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIRRORS = [
    "https://codeload.github.com/mehranranjibin06-source/mega-ai/zip/refs/heads/main",
    "https://ghfast.top/https://github.com/mehranranjibin06-source/mega-ai/archive/refs/heads/main.zip",
    "https://ghproxy.net/https://github.com/mehranranjibin06-source/mega-ai/archive/refs/heads/main.zip",
    "https://gh-proxy.com/https://github.com/mehranranjibin06-source/mega-ai/archive/refs/heads/main.zip",
]
KEEP_DIRS = {"data", "workspace", ".venv", "venv", ".git", "__pycache__", ".pytest_cache", "logs"}
KEEP_FILES = {".env", "mega.db", ".env.local"}


def current_version() -> str:
    try:
        from .config import APP_VERSION
        return APP_VERSION
    except Exception:  # noqa: BLE001
        return "?"


def _read_version(root: Path) -> str:
    f = root / "mega" / "config.py"
    try:
        m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', f.read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except Exception:  # noqa: BLE001
        return "?"


def _download() -> tuple[bytes, str]:
    import httpx
    last = ""
    for url in MIRRORS:
        try:
            with httpx.Client(timeout=180, follow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0 (MegaAI updater)"}) as c:
                r = c.get(url)
            if r.status_code == 200 and len(r.content) > 300_000:
                return r.content, url
            last = f"{url} → {r.status_code} ({len(r.content)} بایت)"
        except Exception as e:  # noqa: BLE001
            last = f"{url} → {type(e).__name__}: {e}"
    raise RuntimeError("دانلود نسخهٔ تازه ناموفق بود — " + last)


def _extract(data: bytes) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="mega-up-"))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        if not any(n.endswith("mega/config.py") for n in names):
            raise RuntimeError("فایل دانلودشده معتبر نیست (ساختار پروژه پیدا نشد)")
        for n in names:                                # جلوگیری از پیمایش مسیر
            tgt = (tmp / n).resolve()
            if not str(tgt).startswith(str(tmp.resolve())):
                raise RuntimeError("آرشیو ناایمن بود")
        z.extractall(tmp)
    inner = [d for d in tmp.iterdir() if d.is_dir()]
    if len(inner) == 1 and (inner[0] / "mega").is_dir():
        return inner[0]
    return tmp


def _copy_over(src: Path, dst: Path) -> list[str]:
    changed: list[str] = []
    for item in sorted(src.rglob("*")):
        rel = item.relative_to(src)
        if any(part in KEEP_DIRS for part in rel.parts):
            continue
        if item.name in KEEP_FILES or item.suffix == ".pyc":
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        new = item.read_bytes()
        old = target.read_bytes() if target.is_file() else None
        if old != new:
            target.write_bytes(new)
            changed.append(str(rel).replace("\\", "/"))
    return changed


def update(force: bool = False) -> dict:
    """نسخهٔ تازه را می‌گیرد و نصب می‌کند. خروجی: نسخهٔ قبل/بعد و فایل‌های عوض‌شده."""
    before = current_version()
    try:
        data, url = _download()
        box = _extract(data)
        after = _read_version(box)
        if not force and after != "?" and after == before:
            shutil.rmtree(box.parent if box.parent.name.startswith("mega-up-") else box, ignore_errors=True)
            return {"ok": True, "before": before, "after": after, "changed": [],
                    "need_restart": False, "from": url,
                    "message": f"برنامه همین حالا آخرین نسخه است (v{before})."}
        changed = _copy_over(box, ROOT)
        for junk in (box, box.parent):
            if junk.name.startswith("mega-up-"):
                shutil.rmtree(junk, ignore_errors=True)
        need = bool(changed)
        return {"ok": True, "before": before, "after": after, "changed": changed[:200],
                "count": len(changed), "need_restart": need, "from": url,
                "message": (f"نسخهٔ {after} نصب شد ({len(changed)} فایل). برای فعال شدن، یک ری‌استارت لازم است."
                            if need else f"همه‌چیز به‌روز است (v{before}).")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "before": before, "error": str(e)}


# ───────────────────────────── ری‌استارت امن ─────────────────────────────
def _script(posix: bool, pid: int) -> str:
    root = str(ROOT)
    if posix:
        return f"""#!/bin/sh
# ری‌استارت خودکار (فقط همین برنامه — به بقیهٔ برنامه‌ها کاری ندارد)
sleep 2
kill -TERM {pid} 2>/dev/null
sleep 3
cd "{root}" || exit 1
nohup {sys.executable} start_vps.py > update_restart.log 2>&1 &
echo "restarted $(date)" >> update_restart.log
"""
    return f"""@echo off
rem ری‌استارت خودکار — فقط همین برنامه (ربات متاتریدر دست نمی‌خورد)
timeout /t 2 /nobreak >nul
taskkill /F /PID {pid} >nul 2>&1
timeout /t 3 /nobreak >nul
cd /d "{root}"
start "" /min cmd /c "python start_vps.py > update_restart.log 2>&1"
"""


def restart(delay_exit: float = 1.5) -> dict:
    """برنامه را روی همان پورت دوباره بالا می‌آورد (فقط پروسهٔ خودمان)."""
    pid = os.getpid()
    posix = os.name != "nt"
    path = ROOT / ("restart.sh" if posix else "restart_update.bat")
    try:
        body = _script(posix, pid)
        if posix:
            path.write_text(body, encoding="utf-8")
            path.chmod(0o755)
            subprocess.Popen(["/bin/sh", str(path)], cwd=str(ROOT),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        else:
            path.write_text(body.replace("\n", "\r\n"), encoding="ascii")
            flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(["cmd", "/c", str(path)], cwd=str(ROOT), close_fds=True,
                             creationflags=flags)
        import threading

        def _bye() -> None:
            time.sleep(delay_exit)
            os._exit(0)                              # خروج تمیز تا اسکریپت ما را دوباره بالا بیاورد

        threading.Thread(target=_bye, daemon=True).start()
        return {"ok": True, "pid": pid, "script": path.name,
                "message": "۱۵ ثانیه صبر کن، بعد صفحه را دوباره باز کن."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e),
                "message": "ری‌استارت خودکار نشد — در CMD این را بزن:  python start_vps.py"}
