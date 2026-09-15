# -*- coding: utf-8 -*-
"""🔄 آپدیت یک‌مرحله‌ای MehranAiShabestar — **مستقل** (از هر نسخه‌ای کار می‌کند، حتی v7).

در CMD داخل پوشهٔ برنامه:

    python update_self.py             # نسخهٔ تازه را می‌گیرد و نصب می‌کند
    python update_self.py --restart   # + برنامه را دوباره بالا می‌آورد و مرورگر را باز می‌کند

هیچ کتابخانه‌ای لازم نیست (فقط پایتون خود ویندوز).

سه لایهٔ دانلود دارد تا در اینترنت ناپایدار هم بگیرد:
  ۱) فایل ZIP از ۶ آینهٔ گیت‌هاب
  ۲) اگر ZIP نشد → فایل‌به‌فایل از CDN های سبک (jsDelivr و آینه‌های raw)

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

def _find_app_root() -> Path:
    """پوشهٔ اصلی برنامه را پیدا می‌کند — حتی اگر این فایل داخل workspace یا کش دانلود شده باشد.

    ترتیب: مسیر داده‌شده با --root → بالا رفتن از محل خود فایل → بالا رفتن از محل اجرا
    → آدرس‌های معمول ویندوز.
    """
    marker = "start_vps.py"

    def ok(d: Path) -> bool:
        return (d / marker).is_file() and (d / "mega" / "config.py").is_file()

    if "--root" in sys.argv:
        try:
            d = Path(sys.argv[sys.argv.index("--root") + 1]).expanduser()
            if ok(d):
                return d
        except Exception:
            pass
    for start in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        d = start
        for _ in range(6):
            if ok(d):
                return d
            if d.parent == d:
                break
            d = d.parent
    home = Path.home()
    for cand in (home / "mega-ai-main", home / "mega-ai", home / "Desktop" / "mega-ai-main",
                 home / "Downloads" / "mega-ai-main", Path("C:/mega-ai-main"), Path("C:/mega-ai")):
        if ok(cand):
            return cand
    return Path(__file__).resolve().parent      # آخرین راه: کنار همین فایل


ROOT = _find_app_root()
OWNER = "mehranranjibin06-source"
REPO = "mega-ai"
BRANCH = "main"

MIRRORS = [
    f"https://gh.llkk.cc/https://github.com/{OWNER}/{REPO}/archive/refs/heads/{BRANCH}.zip",
    f"https://ghproxy.net/https://github.com/{OWNER}/{REPO}/archive/refs/heads/{BRANCH}.zip",
    f"https://ghfast.top/https://github.com/{OWNER}/{REPO}/archive/refs/heads/{BRANCH}.zip",
    f"https://gh-proxy.com/https://github.com/{OWNER}/{REPO}/archive/refs/heads/{BRANCH}.zip",
    f"https://codeload.github.com/{OWNER}/{REPO}/zip/refs/heads/{BRANCH}",
    f"https://github.com/{OWNER}/{REPO}/archive/refs/heads/{BRANCH}.zip",
]

# ── برای حالت جایگزین: فایل‌به‌فایل از CDN
FILES = """server.py
start_vps.py
cli.py
run_local.py
cloud_link.py
make_qr.py
verify_package.py
fix_bat.py
update_self.py
update_now.bat
requirements.txt
mega/__init__.py
mega/addons.py
mega/agent.py
mega/analyze.py
mega/config.py
mega/demo_model.py
mega/ffmpeg_setup.py
mega/free_ai.py
mega/github_tool.py
mega/local_llm.py
mega/media.py
mega/memory.py
mega/orchestrator.py
mega/prereqs.py
mega/providers.py
mega/skills.py
mega/telegram_bot.py
mega/tools.py
mega/tv.py
mega/updater.py
mega/vision.py
mega/templates/find_duplicates.py
mega/templates/organize_files.py
mega/templates/report_tool.py
web/guide.html
web/index.html
web/more.html
web/simple.html
web/terminal.html
web/tv.html""".split()

CDN_BASES = [
    f"https://cdn.jsdelivr.net/gh/{OWNER}/{REPO}@{BRANCH}/",
    f"https://gh.llkk.cc/https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/",
    f"https://ghproxy.net/https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/",
    f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/",
]
KEEP_DIRS = {"data", "workspace", ".venv", "venv", ".git", "__pycache__", ".pytest_cache", "logs"}
KEEP_FILES = {".env", "mega.db", ".env.local"}
UA = {"User-Agent": "Mozilla/5.0 (MegaAI self-updater)"}
TIMEOUT = 120


def say(msg: str) -> None:
    print("  " + msg, flush=True)


def _get(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def current_version() -> str:
    try:
        m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', (ROOT / "mega" / "config.py").read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except Exception:  # noqa: BLE001
        return "?"


def ver_of(path: Path) -> str:
    try:
        m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', (path / "mega" / "config.py").read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except Exception:  # noqa: BLE001
        return "?"


def _write_if_new(rel: str, data: bytes, changed: list[str]) -> None:
    target = ROOT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or target.read_bytes() != data:
        target.write_bytes(data)
        changed.append(rel)


# ───────────────────────── روش ۱: ZIP ─────────────────────────
def try_zip() -> tuple[list[str], str, str]:
    last = ""
    for url in MIRRORS:
        try:
            say(f"⬇️  {url.split('/')[2]} …")
            data = _get(url)
            if len(data) < 300_000:
                last = f"{url} → فقط {len(data)} بایت"
                continue
            tmp = Path(tempfile.mkdtemp(prefix="mega-up-"))
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if not any(n.endswith("mega/config.py") for n in z.namelist()):
                    last = f"{url} → ساختار پروژه نبود"
                    continue
                for n in z.namelist():
                    tgt = (tmp / n).resolve()
                    if not str(tgt).startswith(str(tmp.resolve())):
                        raise RuntimeError("آرشیو ناایمن")
                z.extractall(tmp)
            box = next((d for d in tmp.iterdir() if d.is_dir() and (d / "mega").is_dir()), tmp)
            changed: list[str] = []
            for item in sorted(box.rglob("*")):
                rel = item.relative_to(box)
                if any(part in KEEP_DIRS for part in rel.parts) or item.name in KEEP_FILES or item.suffix == ".pyc":
                    continue
                if item.is_dir():
                    (ROOT / rel).mkdir(parents=True, exist_ok=True)
                    continue
                _write_if_new(str(rel).replace("\\", "/"), item.read_bytes(), changed)
            shutil.rmtree(tmp, ignore_errors=True)
            return changed, ver_of(ROOT), url
        except Exception as e:  # noqa: BLE001
            last = f"{url} → {type(e).__name__}: {e}"
            say(f"   ⚠️ نشد: {type(e).__name__}")
    raise RuntimeError("همهٔ آینه‌های ZIP جواب ندادند — " + last)


# ─────────────────── روش ۲: فایل‌به‌فایل از CDN ───────────────────
def try_files() -> tuple[list[str], str, str]:
    say("🧩 حالت جایگزین: دانلود فایل‌به‌فایل از CDN…")
    changed: list[str] = []
    ok_base, failed = "", []
    for base in CDN_BASES:
        try:                                    # با یک فایل کوچک تست کن
            _get(base + "mega/config.py", timeout=45)
            ok_base = base
            say(f"   ✅ {base.split('/')[2]} پاسخ داد")
            break
        except Exception:  # noqa: BLE001
            say(f"   ⚠️ {base.split('/')[2]} بی‌جواب")
    if not ok_base:
        raise RuntimeError("هیچ CDN ی جواب نداد")
    for rel in FILES:
        got = False
        for base in [ok_base] + [b for b in CDN_BASES if b != ok_base]:
            try:
                data = _get(base + rel, timeout=45)
                if data:
                    _write_if_new(rel, data, changed)
                    got = True
                    break
            except Exception:  # noqa: BLE001
                continue
        if not got:
            failed.append(rel)
    print()
    say(f"   📦 {len(FILES) - len(failed)} از {len(FILES)} فایل گرفته شد"
        + (f" (نگرفته: {', '.join(failed[:5])})" if failed else ""))
    if len(failed) > len(FILES) // 3:
        raise RuntimeError("اینترنت خیلی ناپایدار بود؛ نیمهٔ فایل‌ها نیامد")
    return changed, ver_of(ROOT), ok_base


# ───────────────────────── ری‌استارت ─────────────────────────
def _listeners(ports=(8000, 8001)) -> list[int]:
    pids: list[int] = []
    if os.name != "nt":
        return pids
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=25).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[3] == "LISTENING" and parts[1].rsplit(":", 1)[-1] in {str(p) for p in ports}:
                try:
                    pids.append(int(parts[4]))
                except ValueError:
                    pass
    except Exception:  # noqa: BLE001
        pass
    return sorted(set(pids))


def restart() -> None:
    for pid in _listeners():
        say(f"⏹ بستن اجرای قبلی (PID {pid})")
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    if _listeners():
        time.sleep(3)
    say("🚀 بالا آوردن برنامه…")
    runner = [sys.executable, "start_vps.py"] if os.name == "nt" else ["python3", "start_vps.py"]
    try:
        if os.name == "nt":
            subprocess.Popen(runner, cwd=str(ROOT), close_fds=True,
                             creationflags=0x00000008 | 0x00000200)
        else:
            subprocess.Popen(runner, cwd=str(ROOT), close_fds=True, start_new_session=True)
    except Exception:  # noqa: BLE001
        subprocess.Popen(["python", "start_vps.py"], cwd=str(ROOT), close_fds=True)
    time.sleep(3)
    if os.name == "nt":                     # مرورگر خود وی‌پی‌اس را باز کن
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "http://localhost:8000"], cwd=str(ROOT))
        except Exception:  # noqa: BLE001
            pass
    say("✅ برنامه دوباره روشن شد (۱۵ ثانیه صبر کن، بعد صفحه را باز کن)")


def main() -> int:
    before = current_version()
    print("=" * 66)
    print(f"  MehranAiShabestar — آپدیت خودکار      (نسخهٔ فعلی: v{before})")
    print(f"  پوشهٔ برنامه: {ROOT}")
    print("=" * 66)
    changed: list[str] = []
    src = ""
    try:
        changed, after, src = try_zip()
    except Exception as zip_err:  # noqa: BLE001
        print()
        try:
            changed, after, src = try_files()
        except Exception as file_err:  # noqa: BLE001
            print("\n  ❌ آپدیت نشد.")
            say(str(zip_err))
            say(str(file_err))
            print("\n  راهنما: اینترنت/VPN را روشن کن و همین فایل را دوباره اجرا کن.")
            return 1

    print()
    print(f"  ✅ نسخه: v{before} → v{after}     ({len(changed)} فایل به‌روز شد)")
    for f in changed[:25]:
        print("     -", f)
    if len(changed) > 25:
        print(f"     … و {len(changed) - 25} فایل دیگر")
    print(f"  🔗 منبع: {src[:70]}")
    print("  🔒 دست‌نخورده: .env · data · workspace · .venv")
    if not changed:
        print("  ℹ️  چیز تازه‌ای نبود؛ همین نسخه را داشتی.")
    print("\n  ➡️  فعال‌سازی:  python update_self.py --restart")
    if "--restart" in sys.argv:
        print()
        restart()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
