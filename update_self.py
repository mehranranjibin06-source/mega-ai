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
def _extract_install(data: bytes) -> list[str]:
    """آرشیو ZIP را باز می‌کند و فایل‌های پروژه را روی نصب فعلی می‌ریزد (محافظت‌شده)."""
    if len(data) < 200_000:
        raise RuntimeError(f"آرشیو خیلی کوچک است ({len(data)} بایت)")
    tmp = Path(tempfile.mkdtemp(prefix="mega-up-"))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if not any(n.endswith("mega/config.py") for n in z.namelist()):
            raise RuntimeError("آرشیو، پروژهٔ mega-ai نبود")
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
    return changed


def find_local_zip() -> Path | None:
    """دنبال آرشیو محلی می‌گردد (کنار همین فایل، پوشهٔ برنامه، Downloads…).

    کاربرد: وقتی شبکهٔ ایران گیت‌هاب را باز نمی‌کند، کاربر آرشیو را از چت می‌گیرد
    و همین اسکریپت بدون هیچ اتصال اینترنتی نصبش می‌کند.
    """
    names = ["mega-ai.zip", "mega-ai-main.zip", "mega_ai.zip", "mega-ai (1).zip"]
    here = Path(__file__).resolve().parent
    spots = [here, here.parent, Path.cwd(), Path.cwd().parent, ROOT, ROOT.parent,
             Path.home(), Path.home() / "Downloads", Path.home() / "Desktop"]
    if os.name == "nt":
        for env in ("USERPROFILE", "TEMP", "TMP"):
            v = os.environ.get(env)
            if v:
                spots.append(Path(v))
                spots.append(Path(v) / "Downloads")
    for d in spots:
        try:
            if not d.is_dir():
                continue
        except OSError:
            continue
        for n in names:
            f = d / n
            try:
                if f.is_file() and f.stat().st_size > 200_000:
                    return f
            except OSError:
                continue
    return None


def try_local_zip() -> tuple[list[str], str, str]:
    """نصب از آرشیو محلی — بدون اینترنت."""
    explicit = None
    if "--zip" in sys.argv:
        try:
            explicit = Path(sys.argv[sys.argv.index("--zip") + 1]).expanduser()
        except Exception:  # noqa: BLE001
            explicit = None
    path = explicit if (explicit and explicit.is_file()) else find_local_zip()
    if not path or not path.is_file():
        raise RuntimeError("آرشیو محلی پیدا نشد")
    say(f"📦 نصب از فایل محلی (بدون اینترنت): {path.name}  ({path.stat().st_size // 1024} KB)")
    changed = _extract_install(path.read_bytes())
    return changed, ver_of(ROOT), f"local:{path.name}"


def try_zip() -> tuple[list[str], str, str]:
    last = ""
    for url in MIRRORS:
        try:
            say(f"⬇️  {url.split('/')[2]} …")
            data = _get(url)
            if len(data) < 300_000:
                last = f"{url} → فقط {len(data)} بایت"
                continue
            changed = _extract_install(data)
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
    """ری‌استارت امن: یک دستیار جدا (detached) سرور را می‌بندد و دوباره بالا می‌آورد.

    جدا بودن دستیار مهم است، چون ممکن است این دستور از داخل خود برنامه (کارگزار)
    اجرا شود؛ آن‌وقت سرور بسته می‌شود ولی دستیار مستقل ادامه می‌دهد.
    """
    pids = _listeners()
    runner = "python start_vps.py" if os.name == "nt" else "python3 start_vps.py"
    if os.name == "nt":
        kills = "\r\n".join(f"taskkill /F /PID {p} >nul 2>&1" for p in pids)
        bat = (
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            f"{kills}\r\n"
            "timeout /t 3 /nobreak >nul\r\n"
            f'cd /d "{ROOT}"\r\n'
            "set PY=python\r\n"
            "where python >nul 2>&1 || set PY=py\r\n"
            "where %PY% >nul 2>&1\r\n"
            'if errorlevel 1 (echo Python not found. Install Python 3 and tick Add-to-PATH. > update_restart.log & exit /b 1)\r\n'
            'start "" /min cmd /c "%PY% start_vps.py > update_restart.log 2>&1"\r\n'
            'start "" "http://localhost:8000"\r\n'
        )
        helper = ROOT / "_restart_helper.bat"
        helper.write_text(bat, encoding="ascii", newline="")
        say(f"⏹ بستن اجرای قبلی ({len(pids)} فرایند) و روشن کردن دوباره…")
        subprocess.Popen(["cmd", "/c", str(helper)], cwd=str(ROOT), close_fds=True,
                         creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS
    else:
        for pid in pids:
            say(f"⏹ بستن اجرای قبلی (PID {pid})")
            subprocess.run(["kill", "-TERM", str(pid)], capture_output=True)
        time.sleep(3)
        say("🚀 بالا آوردن برنامه…")
        subprocess.Popen(["python3", "start_vps.py"], cwd=str(ROOT), close_fds=True,
                         start_new_session=True)
    say("✅ دستور ری‌استارت داده شد — ۲۰ ثانیه صبر کن، بعد صفحه را رفرش کن.")


def main() -> int:
    before = current_version()
    print("=" * 66)
    print(f"  MehranAiShabestar — آپدیت خودکار      (نسخهٔ فعلی: v{before})")
    print(f"  پوشهٔ برنامه: {ROOT}")
    print("=" * 66)
    changed: list[str] = []
    src = ""
    zip_err = file_err = None
    done = False

    def _explicit_zip() -> bool:
        if "--zip" not in sys.argv:
            return False
        try:
            return Path(sys.argv[sys.argv.index("--zip") + 1]).expanduser().is_file()
        except Exception:  # noqa: BLE001
            return False

    # ترتیب مهم است: اول آرشیو دستی (اگر خودت دادی) → بعد اینترنت → و آخر از همه
    # آرشیوی که «تصادفی» در پوشه‌ها پیدا شود (چون ممکن است نسخهٔ قدیمی باشد).
    if _explicit_zip():
        try:
            changed, after, src = try_local_zip()
            done = True
        except Exception as e1:  # noqa: BLE001
            zip_err = e1
    if not done:
        print()
        try:                                 # ۱) آینه‌های ZIP
            changed, after, src = try_zip()
            done = True
        except Exception as e2:  # noqa: BLE001
            zip_err = e2
    if not done:
        print()
        try:                                 # ۲) فایل‌به‌فایل از CDN
            changed, after, src = try_files()
            done = True
        except Exception as e3:  # noqa: BLE001
            file_err = e3
    if not done:
        try:                                 # ۳) آخرین راه: آرشیو محلی (بدون اینترنت)
            say("🌐 اینترنت جواب نداد — نصب از آرشیو محلی (ممکن است نسخهٔ قدیمی‌تر باشد)…")
            changed, after, src = try_local_zip()
            done = True
        except Exception as e4:  # noqa: BLE001
            file_err = e4

    if not done:
        print("\n  ❌ آپدیت نشد — هیچ راهی باز نشد (اینترنت گیت‌هاب/CDN را بسته است).")
        say(f"آینه‌ها: {zip_err}")
        say(f"CDN: {file_err}")
        print("\n  راه‌حل بدون اینترنت:")
        print("    ۱) فایل mega-ai.zip را از چت بگیر و بگذارش کنار همین فایل")
        print("    ۲) دوباره اجرا کن:  python update_self.py --zip mega-ai.zip --restart")
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
