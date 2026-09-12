#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""بازرسی کامل بسته: زیپ را باز می‌کند و خطاهای احتمالی ویندوز را تک‌تک چک می‌کند."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import venv
import zipfile
from pathlib import Path

ZIP = Path("/home/user/mega-ai.zip")
OUT = Path("/tmp/pkgcheck")
FAILS: list[str] = []
WARNS: list[str] = []


def ok(label: str, good: bool, detail: str = "") -> None:
    mark = "OK  " if good else "FAIL"
    print(f"  [{mark}] {label}" + (f"  ({detail})" if detail else ""))
    if not good:
        FAILS.append(label)


def warn(label: str, detail: str = "") -> None:
    print(f"  [warn] {label}" + (f"  ({detail})" if detail else ""))
    WARNS.append(label)


print("=" * 62)
print("   بازرسی بسته‌ی تحویلی")
print("=" * 62)

# ── ۱) زیپ سالم است و باز می‌شود
print("\n۱) زیپ")
ok("فایل زیپ موجود است", ZIP.exists(), f"{ZIP.stat().st_size/1024/1024:.1f} MB" if ZIP.exists() else "")
if not ZIP.exists():
    sys.exit(1)
with zipfile.ZipFile(ZIP) as z:
    bad = z.testzip()
    ok("داده فشرده سالم است", bad is None, str(bad) if bad else "")
    names = z.namelist()

shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
with zipfile.ZipFile(ZIP) as z:
    z.extractall(OUT)
roots = [p for p in OUT.iterdir() if p.is_dir()]
ok("یک پوشه‌ی ریشه دارد", len(roots) == 1, roots[0].name if roots else "")
ROOT = roots[0]

# ── ۲) فایل‌های دستور ویندوز (.bat)
print("\n۲) فایل‌های .bat (خطای «not recognized» از همین‌جا می‌آمد)")
bats = sorted(ROOT.glob("*.bat"))
ok("فایل bat وجود دارد", bool(bats), ", ".join(b.name for b in bats))
for b in bats:
    raw = b.read_bytes()
    crlf = raw.count(b"\r\n")
    lone_lf = raw.count(b"\n") - crlf
    non_ascii = sum(1 for byte in raw if byte > 127)
    bom = raw.startswith(b"\xef\xbb\xbf")
    lines = [l for l in raw.decode("ascii", "ignore").splitlines() if l.strip()]
    ok(f"{b.name}: پایان‌خط ویندوزی", lone_lf == 0, f"CRLF={crlf}, LF تنها={lone_lf}")
    ok(f"{b.name}: فقط حروف انگلیسی", non_ascii == 0, f"بایت غیرانگلیسی={non_ascii}")
    ok(f"{b.name}: بدون BOM", not bom)
    ok(f"{b.name}: کوتاه و ساده", len(lines) <= 20, f"{len(lines)} خط")

# ── ۳) فایل‌هایی که bat صدا می‌زند موجودند؟
print("\n۳) وابستگی فایل‌های bat")
for b in bats:
    text = b.read_text(encoding="ascii", errors="ignore")
    for m in re.finditer(r"\b([\w./\\-]+\.py)\b", text):
        target = ROOT / m.group(1).replace("\\", "/")
        ok(f"{b.name} → {m.group(1)} موجود است", target.is_file())

# ── ۴) فایل‌های ضروری
print("\n۴) فایل‌های ضروری")
for rel in ("server.py", "requirements.txt", "start_vps.py", "run_local.py", "cloud_link.py",
            "make_qr.py", "fix_bat.py", "mega/prereqs.py", "mega/agent.py", "web/simple.html",
            "web/index.html", "assets/fonts/Vazirmatn-Bold.ttf", "assets/logo_icon_256.png",
            "assets/favicon.ico", "README-FIRST.txt", "START_HERE.md"):
    ok(rel, (ROOT / rel).is_file())

# ── ۵) کد پایتون بدون خطای نحوی (روی ۳.۱۱ که سرور کاربر دارد)
print("\n۵) نحو کد پایتون (روی پایتون 3.11)")
py311 = None
for cand in ("python3.11", "/home/user/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11"):
    if shutil.which(cand) or Path(cand).exists():
        py311 = cand
        break
if not py311:
    try:
        subprocess.run(["uv", "python", "install", "3.11"], capture_output=True, timeout=300)
        p = Path.home() / ".local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11"
        py311 = str(p) if p.exists() else None
    except Exception:
        py311 = None
if py311:
    bad_files = []
    for f in sorted(ROOT.rglob("*.py")):
        r = subprocess.run([py311, "-m", "py_compile", str(f)], capture_output=True, text=True)
        if r.returncode != 0:
            bad_files.append(f"{f.relative_to(ROOT)}: {r.stderr.strip().splitlines()[-1][:80]}")
    ok(f"همه‌ی {len(list(ROOT.rglob('*.py')))} فایل پایتون کامپایل شد", not bad_files,
       "; ".join(bad_files[:3]) if bad_files else "")
else:
    warn("پایتون ۳.۱۱ پیدا نشد؛ با نسخه‌ی فعلی چک شد")

# ── ۶) نصب کامل از داخل همین زیپ + اجرای برنامه
print("\n۶) نصب و اجرا از داخل بسته (محیط تازه)")
VENV = Path("/tmp/pkgvenv")
shutil.rmtree(VENV, ignore_errors=True)
venv.create(VENV, with_pip=True)
py = str(VENV / "bin/python")
env = {**os.environ, "PYTHONPATH": str(ROOT)}
t0 = time.time()
r = subprocess.run([py, str(ROOT / "mega" / "prereqs.py")], cwd=str(ROOT), env=env,
                   capture_output=True, text=True, timeout=2400)
took = round(time.time() - t0, 1)
tail = [l for l in (r.stdout or "").splitlines() if "غایب" in l or "کتابخانه" in l or "نصب" in l]
ok("نصب خودکار کتابخانه‌ها", "'missing_pkgs': []" in (r.stdout or ""), f"{took}s")
for line in tail[-3:]:
    print("      ", line.strip())

env2 = {**os.environ, "MEGA_NO_VENV": "1", "PORT": "8801", "MEGA_HOST": "127.0.0.1"}
proc = subprocess.Popen([py, str(ROOT / "server.py")], cwd=str(ROOT), env=env2,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
import urllib.request
alive = False
for _ in range(45):
    time.sleep(1)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8801/api/health", timeout=3) as resp:
            alive = resp.status == 200
            break
    except Exception:
        if proc.poll() is not None:
            break
ok("برنامه از داخل بسته بالا آمد (/api/health)", alive)
if not alive:
    out = proc.stdout.read() if proc.stdout else ""
    print("      خروجی سرور:", out[-500:])
if proc.poll() is None:
    proc.terminate()
    time.sleep(1)
    proc.kill()

# ── ۷) جلوگیری از لو رفتن اطلاعات خصوصی
print("\n۷) امنیت بسته")
ok("فایل .env داخل بسته نیست", not (ROOT / ".env").exists())
ok("پوشه‌ی .venv داخل بسته نیست", not (ROOT / ".venv").exists())
ok("پوشه‌ی .git داخل بسته نیست", not (ROOT / ".git").exists())
leaks = [n for n in names if "/data/" in n and not n.endswith("/")]
leaks += [n for n in names if n.endswith("mega.db")]
ok("داده‌ی خصوصی داخل بسته نیست", not leaks, ", ".join(leaks[:3]))
ok(".env.example برای راهنما موجود است", (ROOT / ".env.example").is_file())

# ── نتیجه
print("\n" + "=" * 62)
if FAILS:
    print(f"  نتیجه: {len(FAILS)} خطا ❌")
    for f in FAILS:
        print("   -", f)
else:
    print(f"  نتیجه: هیچ خطایی پیدا نشد ✅  ({len(WARNS)} هشدار)")
print("=" * 62)
sys.exit(1 if FAILS else 0)
