#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""شبیه‌سازی خرابی سرور کاربر: venv بدون pip → آیا برنامه خودش تعمیرش می‌کند؟"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VP = ROOT / ".venv"
PY = VP / "bin/python"

print("۱) پاک‌کردن .venv و ساخت محیطی که pip ندارد (همان باگ ویندوز) …")
shutil.rmtree(VP, ignore_errors=True)
r = subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", "--without-pip", str(VP)],
                   capture_output=True, text=True)
print("   ساخته شد:", r.returncode == 0, "| pip دارد؟",
      subprocess.run([str(PY), "-m", "pip", "--version"], capture_output=True).returncode == 0)

print("\n۲) حالا دقیقاً همان کاری را می‌کنیم که برنامه می‌کند …")
sys.path.insert(0, str(ROOT))
from run_local import ensure_venv, has_pip  # noqa: E402

env_backup = os.environ.pop("MEGA_NO_VENV", None)
t0 = time.time()
py = ensure_venv()
took = round(time.time() - t0, 1)
print(f"   نتیجه: {py}")
print(f"   زمان تعمیر: {took} ثانیه")
print("   pip در آن هست؟", has_pip(py) if py.endswith(("python", "python.exe")) else "—")

if not py.endswith(("python", "python.exe")):
    print("   ❌ fallback به پایتون سیستم رفت (تعمیر نشد)")
    sys.exit(1)

print("\n۳) نصب کتابخانه‌ها با همان پایتون …")
from mega.prereqs import ensure_all  # noqa: E402
res = ensure_all(py, install=True)
print("   نتیجه:", {k: v for k, v in res.items() if k in ("installed", "missing_pkgs")})

print("\n۴) اجرای سرور با همان مفسر …")
env = {**os.environ, "MEGA_NO_VENV": "1", "PORT": "8811", "MEGA_HOST": "127.0.0.1"}
proc = subprocess.Popen([py, str(ROOT / "server.py")], cwd=str(ROOT), env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
import urllib.request
alive = False
for _ in range(40):
    time.sleep(1)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8811/api/health", timeout=3) as resp:
            alive = resp.status == 200
            break
    except Exception:
        if proc.poll() is not None:
            break
if not alive and proc.stdout:
    print("   خروجی:", proc.stdout.read()[-400:])
print("   /api/health →", "200 ✅" if alive else "ناموفق ❌")
if proc.poll() is None:
    proc.terminate()
    time.sleep(1)
    proc.kill()

print("\nنتیجه:", "✅ تعمیر خودکار کار می‌کند" if alive else "❌ هنوز مشکل دارد")
