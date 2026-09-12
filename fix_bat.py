# -*- coding: utf-8 -*-
"""fix_bat.py — فایل‌های ویندوزی را سالم می‌کند: CRLF + بدون حرف غیرانگلیسی.

روی این پروژه همیشه بعد از ویرایش *.bat یک‌بار اجرا شود:
    python3 fix_bat.py
"""
from pathlib import Path

changed = []
for p in sorted(Path(".").glob("*.bat")):
    raw = p.read_bytes()
    new = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    nonascii = [b for b in new if b > 127]
    if new != raw:
        p.write_bytes(new)
        changed.append(p.name)
    flag = "OK" if not nonascii else f"دارای {len(nonascii)} بایت غیرانگلیسی ❌"
    print(f"  {p.name:22s} CRLF ✅  {flag}")

print("اصلاح‌شده:", ", ".join(changed) if changed else "(چیزی لازم نبود)")
