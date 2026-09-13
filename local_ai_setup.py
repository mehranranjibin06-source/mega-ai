# -*- coding: utf-8 -*-
"""
local_ai_setup.py — نصب «هوشِ خودِ سرور» (Ollama + یک مدل کوچک).

بعد از این کار، برنامه بدون هیچ کلید API و بدون اینترنت جواب می‌دهد، چون مدل
واقعاً روی همین کامپیوتر اجرا می‌شود.

اجرا:   python local_ai_setup.py            (خودش اندازه‌ی رم را می‌بیند و مدل مناسب را می‌آورد)
        python local_ai_setup.py --small    (مدل کوچک‌تر، برای رم کم)
        python local_ai_setup.py --model qwen2.5:3b
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

FORCE_EN = os.name == "nt" and (os.environ.get("MEGA_LANG") or "").lower() != "fa"


def say(fa: str, en: str) -> None:
    print(en if FORCE_EN else fa, flush=True)


def total_ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:  # noqa: BLE001
        return 0.0


def pick_model(args: list[str]) -> str:
    """بزرگ‌ترین مغزی که این سرور می‌کشد را انتخاب می‌کند.

    راهنما (نسخه‌ی فشرده Q4): هر میلیارد پارامتر ≈ ۰.۷ گیگ رم.
    سرور ۲ گیگی → ۱.۵B ، ۸ گیگی → ۷B ، ۱۶ گیگی → ۱۴B ، ۳۲ گیگی → ۳۲B
    """
    if "--model" in args:
        return args[args.index("--model") + 1]

    ram = total_ram_gb()
    free = max(0.0, ram - 1.5)          # ۱.۵ گیگ برای ویندوز و ربات معامله‌گر
    tiers = [
        (50.0, "llama3.3:70b", "نزدیک به بهترین‌های جهان (رم ~۴۸ گیگ)"),
        (28.0, "qwen2.5:32b", "هوش بالا (رم ~۳۲ گیگ)"),
        (13.0, "qwen2.5:14b", "خوب (رم ~۱۶ گیگ)"),
        (6.0, "qwen2.5:7b", "قابل قبول (رم ~۸ گیگ)"),
        (3.0, "llama3.2:3b", "سبک (رم ~۴ گیگ)"),
        (1.4, "qwen2.5:1.5b", "کوچک (رم ~۲ گیگ)"),
        (0.0, "qwen2.5:0.5b", "خیلی کوچک"),
    ]
    for need, model, label in tiers:
        if free >= need:
            if ram:
                say(f"🧮 رم سرور: {ram:.1f} گیگ → انتخاب شد: {model}   [{label}]",
                    f"[i] Server RAM {ram:.1f} GB -> selected: {model}  [{label}]")
            return model
    return "qwen2.5:0.5b"


def explain_tiers() -> None:
    say("📊 مغز بزرگ‌تر = رم بیشتر:", "[i] Bigger brain needs more RAM:")
    for line in ("   ۰.۵B ← ۱ گیگ رم      |      ۷B ← ۸ گیگ رم",
                 "   ۱.۵B ← ۲ گیگ رم      |     ۱۴B ← ۱۶ گیگ رم",
                 "    ۳B ← ۴ گیگ رم      |     ۳۲B ← ۳۲ گیگ رم",
                 "                        |     ۷۰B ← ۴۸ گیگ رم"):
        print("   " + line)


def install_ollama() -> bool:
    if shutil.which("ollama"):
        say("✅ Ollama از قبل نصب است.", "[OK] Ollama is already installed.")
        return True
    say("⬇️  Ollama نصب نیست — الان نصبش می‌کنم (یک‌بار برای همیشه) …",
        "[...] Installing Ollama (one time only) ...")
    cmds = []
    if os.name == "nt":
        if shutil.which("winget"):
            cmds.append(["winget", "install", "-e", "--id", "Ollama.Ollama", "--silent",
                         "--accept-package-agreements", "--accept-source-agreements"])
        cmds.append(["powershell", "-c",
                     "iwr https://ollama.com/download/OllamaSetup.exe -OutFile $env:TEMP\\ollama.exe; "
                     "Start-Process $env:TEMP\\ollama.exe -ArgumentList '/S' -Wait"])
    else:
        cmds.append(["bash", "-lc", "curl -fsSL https://ollama.com/install.sh | sh"])
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, timeout=3600)
            if r.returncode == 0 and shutil.which("ollama"):
                say("✅ Ollama نصب شد.", "[OK] Ollama installed.")
                return True
        except Exception as e:  # noqa: BLE001
            say(f"⚠️  {type(e).__name__} — راه بعدی را امتحان می‌کنم.", f"[!] {type(e).__name__} - trying next way.")
    say("❌ نصب خودکار Ollama نشد.", "[!] Could not install Ollama automatically.")
    say("   دستی: به https://ollama.com/download برو و نصب کن، بعد این فایل را دوباره اجرا کن.",
        "   Manual: download from https://ollama.com/download, then run this file again.")
    return False


def wait_for_server(seconds: int = 90) -> bool:
    from mega import local_llm
    say("⏳ منتظر روشن شدن هوش محلی …", "[...] waiting for the local AI to start ...")
    for _ in range(seconds):
        if local_llm.detect():
            return True
        time.sleep(1)
    return False


def start_ollama() -> None:
    """در ویندوز معمولاً سرویس خودش بالا می‌آید؛ اگر نه، دستی اجرا کن."""
    if wait_for_server(20):
        return
    try:
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        try:
            subprocess.Popen([str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" /
                                  "Ollama" / "ollama.exe"), "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:  # noqa: BLE001
            pass
    wait_for_server(60)


def pull_model(model: str) -> bool:
    say(f"⬇️  دانلود مدل «{model}» (یک‌بار؛ اگر نت قطع شد، همین دستور را دوباره بزن — ادامه می‌دهد)",
        f"[...] Downloading model '{model}' (one time; re-run this file if the net drops - it resumes)")
    try:
        r = subprocess.run(["ollama", "pull", model], timeout=7200)
        return r.returncode == 0
    except Exception as e:  # noqa: BLE001
        say(f"⚠️  دانلود ناتمام ماند ({type(e).__name__}).", f"[!] Download did not finish ({type(e).__name__}).")
        return False


def main() -> int:
    args = sys.argv[1:]
    print("=" * 62)
    say("   هوش روی سرور خودت — نصب یک‌باره", "   AI on your own server - one-time setup")
    print("=" * 62 + "\n")

    ram = total_ram_gb()
    if ram:
        say(f"🧮 رم سرور: {ram:.1f} گیگابایت", f"[i] Server RAM: {ram:.1f} GB")
    explain_tiers()

    if not install_ollama():
        return 1
    start_ollama()

    model = pick_model(args)
    ok_model = pull_model(model)
    found = wait_for_server(10)

    print()
    if found and ok_model:
        say(f"✅ تمام! هوش «{model}» روی سرور خودت آماده است.",
            f"[OK] Done! '{model}' is now running on your own server.")
        say("   حالا برنامه را اجرا کن:  python start_vps.py",
            "   Now start the app:  python start_vps.py")
        say("   برنامه خودش این هوش را پیدا می‌کند — بدون کلید API.",
            "   The app detects it automatically - no API key needed.")
        return 0
    if found:
        say("⚠️  Ollama روشن است ولی دانلود مدل کامل نشد. همین دستور را دوباره بزن:",
            "[!] Ollama is running but the model download is incomplete. Re-run:")
        say(f"   ollama pull {model}", f"   ollama pull {model}")
        return 1
    say("⚠️  Ollama نصب شد ولی سرورش روشن نشد. یک‌بار:  ollama serve",
        "[!] Ollama installed but its server is not up. Run once:  ollama serve")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
