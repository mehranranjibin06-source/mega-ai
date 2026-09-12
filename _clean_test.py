#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تست تمیز راه‌اندازی سرور روی پورت سفارشی (بدون کشتن اشتباهی پروسه‌ها)"""
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 8500
PW = "mahan"


def listening_pids(port: int) -> list[int]:
    try:
        out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True).stdout
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        if f":{port} " in line and "pid=" in line:
            for part in line.split("pid=")[1:]:
                pid = part.split(",")[0]
                if pid.isdigit():
                    pids.append(int(pid))
    return pids


def kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
        print(f"  کشته شد: pid={pid}")
    except Exception as e:  # noqa: BLE001
        print(f"  (pid={pid}: {e})")


for pid in listening_pids(PORT) + listening_pids(PORT + 1):
    kill(pid)
time.sleep(1)

env = {**os.environ, "MEGA_PASSWORD": PW, "PORT": str(PORT), "MEGA_NO_VENV": "1"}
log = open("/tmp/clean_run.log", "w")
proc = subprocess.Popen([sys.executable, "start_vps.py"], cwd=str(ROOT), env=env,
                        stdout=log, stderr=subprocess.STDOUT)
print("  اجرا شد، ۲۲ ثانیه صبر …")
time.sleep(22)

print("\n--- خروجی start_vps.py ---")
print(Path("/tmp/clean_run.log").read_text(encoding="utf-8")[:1400])

print("--- دسترسی با رمز ---")
try:
    import base64
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/")
    req.add_header("Authorization", "Basic " + base64.b64encode(f"1:{PW}".encode()).decode())
    with urllib.request.urlopen(req, timeout=8) as r:
        body = r.read().decode("utf-8", "ignore")
        print("  کد:", r.status)
        i = body.find("<title>")
        print("  عنوان:", body[i:i + 60] if i >= 0 else "(پیدا نشد)")
except Exception as e:  # noqa: BLE001
    print("  ❌", e)

try:
    urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=6)
    print("  ❌ بدون رمز هم باز شد!")
except Exception as e:  # noqa: BLE001
    print("  بدون رمز →", getattr(e, "code", e))

print("--- پاک‌سازی ---")
try:
    proc.terminate()
except Exception:
    pass
for pid in listening_pids(PORT) + listening_pids(PORT + 1):
    kill(pid)
envfile = ROOT / ".env"
if envfile.exists():
    envfile.unlink()
    print("  .env پاک شد")
print("تمام.")
