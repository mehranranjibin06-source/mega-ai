# -*- coding: utf-8 -*-
"""🔄 آپدیت از خط فرمان (نسخهٔ متنی همان دکمهٔ داخل برنامه).

استفاده در CMD داخل پوشهٔ برنامه:

    python update_self.py            # نسخهٔ تازه را می‌گیرد و نصب می‌کند
    python update_self.py --restart  # بعد از نصب، خودش برنامه را دوباره بالا می‌آورد
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mega import updater      # noqa: E402


def main() -> int:
    restart = "--restart" in sys.argv
    force = "--force" in sys.argv
    print("=" * 62)
    print(f"  MehranAiShabestar — آپدیت   (نسخهٔ فعلی: v{updater.current_version()})")
    print("=" * 62)
    print("  در حال دانلود از GitHub (۴ آدرس پشت‌سرهم امتحان می‌شود)…")
    res = updater.update(force=force)
    if not res.get("ok"):
        print("\n  ❌ آپدیت نشد:")
        print("   ", res.get("error"))
        print("\n  چند لحظه بعد دوباره امتحان کن (اینترنت قطع و وصل می‌شود).")
        return 1

    print(f"\n  ✅ نسخهٔ نصب‌شده: v{res['before']} → v{res['after']}")
    if res.get("count"):
        print(f"  {res['count']} فایل به‌روز شد:")
        for f in res["changed"][:40]:
            print("   -", f)
    else:
        print("  همه‌چیز از قبل به‌روز بود.")
    print("  🔒 دست‌نخورده: .env ، data ، workspace ، .venv")

    if res.get("need_restart"):
        if restart:
            print("\n  🔄 ری‌استارت… (۱۵ ثانیه بعد صفحه را دوباره باز کن)")
            print("   ", updater.restart().get("message"))
        else:
            print("\n  برای فعال شدن، برنامه را ببند و دوباره اجرا کن:  python start_vps.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
