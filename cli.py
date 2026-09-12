#!/usr/bin/env python3
"""
MEGA-AI  |  خط فرمان (CLI)
------------------------------------------------
  python cli.py "هر پرامپتی"                 → اجرای کامل با پنل خبرگان
  python cli.py -m deep "پرامپت"             → حالت عمیق (خبره بیشتر + نقد دو دور)
  python cli.py -m code "یک ربات تلگرام بساز" → حالت کد (ابزار اجرا فعال)
  python cli.py --keys                       → وضعیت کلیدها
  python cli.py --set-key OPENAI_API_KEY=sk-… → ذخیره‌ی کلید
  python cli.py --models                     → لیست مدل‌های در دسترس
  python cli.py --rank                        → جدول اعتماد مدل‌ها
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from mega.config import SETTINGS, configured_providers, has_any_key, key_status, save_keys
from mega.memory import MEMORY
from mega.orchestrator import run_once


def cmd_keys() -> None:
    print("\n🔑 وضعیت کلیدهای API:\n")
    st = key_status()
    for pid, info in st.items():
        mark = "✅ فعال" if info["configured"] else "❌ تنظیم نشده"
        print(f"  {mark:<14} {info['label']}")
        if not info["configured"]:
            print(f"                 کلید: {info['env_key']}  ←  {info['signup']}")
    print(f"\n  پرووایدرهای فعال: {len(configured_providers())}  |  "
          f"{'حالت واقعی' if has_any_key() else 'حالت نمایشی (DEMO)'}\n")


async def cmd_models() -> None:
    from mega.providers import list_models
    for p in configured_providers():
        ms = await list_models(p.id)
        print(f"\n📦 {p.label} — {len(ms)} مدل")
        for m in ms[:40]:
            print("   -", m)


def cmd_rank() -> None:
    rows = MEMORY.leaderboard()
    if not rows:
        print("\nهنوز داده‌ای نیست؛ اول چند پرامپت اجرا کن.\n"); return
    print("\n🏆 جدول اعتماد مدل‌ها (میانگین امتیاز داوران):\n")
    print(f"  {'امتیاز':<8}{'مدل':<42}{'نوع کار':<12}{'اجرا':<6}")
    for r in rows:
        print(f"  {r['avg']:<8}{r['model'][:40]:<42}{r['task_type']:<12}{r['runs']:<6}")
    print()


async def main() -> None:
    ap = argparse.ArgumentParser(description="MEGA-AI — ارکستراتور چند-هوشی")
    ap.add_argument("prompt", nargs="*", help="پرامپت")
    ap.add_argument("-m", "--mode", default="panel", choices=["fast", "panel", "deep", "all", "code"])
    ap.add_argument("-s", "--session", default="cli", help="شناسه‌ی نشست (برای ادامه‌ی گفتگو)")
    ap.add_argument("--keys", action="store_true", help="وضعیت کلیدها")
    ap.add_argument("--set-key", action="append", default=[], metavar="NAME=value")
    ap.add_argument("--models", action="store_true", help="لیست مدل‌ها")
    ap.add_argument("--rank", action="store_true", help="جدول اعتماد مدل‌ها")
    ap.add_argument("--live", action="store_true", help="استریم خام توکن‌به‌توکن")
    ap.add_argument("--quiet", action="store_true", help="فقط پاسخ نهایی")
    ap.add_argument("--panel", type=int, help="تعداد خبره‌ها")
    args = ap.parse_args()

    if args.set_key:
        pairs = {}
        for item in args.set_key:
            if "=" in item:
                k, v = item.split("=", 1)
                pairs[k.strip().upper()] = v.strip()
        save_keys(pairs)
        print("ذخیره شد ✅")
        cmd_keys()
        return
    if args.keys:
        cmd_keys(); return
    if args.models:
        await cmd_models(); return
    if args.rank:
        cmd_rank(); return

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        ap.print_help(); return
    if args.panel:
        SETTINGS.panel_size = args.panel
    if args.mode == "code":
        SETTINGS.use_tools = True
    if args.mode == "fast":
        SETTINGS.verify = False

    if not has_any_key():
        print("\n⚠️  هیچ کلید API ثبت نشده؛ اجرا در حالت نمایشی (DEMO) انجام می‌شود.")
        print("    برای اتصال واقعی:  python cli.py --set-key OPENROUTER_API_KEY=sk-or-...\n")

    print(f"\n{'═'*64}\n🧠 MEGA-AI  |  حالت: {args.mode}  |  نشست: {args.session}\n{'═'*64}")
    final = await run_once(prompt, session_id=args.session, mode=args.mode,
                           settings=SETTINGS,
                           printer=None if args.quiet else ("live" if args.live else "summary"))
    print(f"\n\n{'━'*64}\n🏁 پاسخ نهایی\n{'━'*64}\n{final}\n")

    det = MEMORY.sessions(1)
    if det:
        print(f"🗂  جزئیات کامل در پایگاه‌داده ذخیره شد (mega-ai/data/mega.db)\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
