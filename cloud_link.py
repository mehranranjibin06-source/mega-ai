#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cloud_link.py — «ابرهوش» را روی لپ‌تاپ خودت اجرا کن و یک لینک عمومی بگیر.

چه کار می‌کند؟
  1) اگر سرور بالا نیست، خودش server.py را اجرا می‌کند (پورت پیش‌فرض ۸۰۰۰)
  2) cloudflared را (اگر نباشد) خودش دانلود می‌کند و تونل سریع می‌سازد
  3) لینک عمومی https://....trycloudflare.com را چاپ می‌کند + پوستر QR می‌سازد

نکته‌ی مهم: لینک تا وقتی این پنجره باز است زنده می‌ماند (لپ‌تاپ روشن = لینک باز).
پس این با «سرور ابری» که من داخل چت می‌ساختم فرق دارد: این پاک نمی‌شود.

اجرا:   python cloud_link.py
گزینه‌ها:  --port 8000   --no-server   --no-qr   --cloudflared PATH
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


# ───────────────────────── ابزارها ─────────────────────────
def log(msg: str = "") -> None:
    print(msg, flush=True)


def asset_for_platform() -> tuple[str, str | None]:
    """(نام فایل دانلود، پسوند استخراج) برای سیستم‌عامل فعلی."""
    sysname = platform.system().lower()
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")

    if sysname == "windows":
        return ("cloudflared-windows-amd64.exe" if not arm else "cloudflared-windows-arm64.exe", None)
    if sysname == "darwin":
        name = "cloudflared-darwin-arm64.tgz" if arm else "cloudflared-darwin-amd64.tgz"
        return (name, ".tgz")
    # linux
    return ("cloudflared-linux-arm64" if arm else "cloudflared-linux-amd64", None)


def find_cloudflared(explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.exists() else None
    env = os.environ.get("CLOUDFLARED")
    if env and Path(env).expanduser().exists():
        return Path(env).expanduser()
    on_path = shutil.which("cloudflared")
    if on_path:
        return Path(on_path)
    for cand in (TOOLS / "cloudflared", TOOLS / "cloudflared.exe", TOOLS / "cloudflared-darwin"):
        if cand.exists():
            return cand
    return None


def download_cloudflared() -> Path:
    name, kind = asset_for_platform()
    TOOLS.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/{name}"
    raw = TOOLS / name
    log(f"⬇️  دانلود cloudflared ({name}) …")
    urllib.request.urlretrieve(url, raw)

    if kind == ".tgz":
        target = TOOLS / "cloudflared"
        with tarfile.open(raw, "r:gz") as tf:
            for m in tf.getmembers():
                if m.name.endswith("cloudflared"):
                    m.name = "cloudflared"
                    tf.extract(m, TOOLS)
                    break
        raw.unlink(missing_ok=True)
        binpath = target
    else:
        binpath = TOOLS / ("cloudflared.exe" if name.endswith(".exe") else "cloudflared")
        if raw != binpath:
            raw.replace(binpath)

    try:
        binpath.chmod(0o755)
    except Exception:
        pass
    log(f"✅ cloudflared آماده شد: {binpath}")
    return binpath


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


def lan_ip() -> str:
    """آی‌پی واقعی شبکه‌ی محلی (link-local و لوکال را نادیده می‌گیرد)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
    except Exception:
        return ""
    if ip.startswith("169.254.") or ip.startswith("127."):
        return ""
    return ip


# ───────────────────────── QR ─────────────────────────
def make_qr(url: str, out: Path) -> bool:
    try:
        import qrcode
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        log("ℹ️  qrcode/Pillow نصب نیست → پوستر QR ساخته نشد (pip install qrcode pillow)")
        return False

    W, H = 1000, 1300
    BG, CARD, ACCENT, TXT, MUTED = (13, 17, 28), (24, 31, 46), (86, 156, 255), (235, 240, 248), (150, 163, 184)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([40, 40, W - 40, H - 40], radius=36, fill=CARD, outline=(45, 58, 82), width=3)

    def font(size: int):
        for name in ("Vazirmatn-Bold.ttf", "Vazirmatn-Regular.ttf"):
            p = ROOT / "assets" / "fonts" / name
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def center(y: int, text: str, f, fill) -> None:
        d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)

    center(92, "MehranAiShabestar", font(56), TXT)
    center(186, "مهران‌هوش شبستر — هوش مصنوعی شخصی", font(32), MUTED)

    qr = qrcode.QRCode(box_size=10, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="black", back_color="white").convert("RGB").resize((560, 560))
    qx, qy = (W - 560) // 2, 268
    d.rounded_rectangle([qx - 18, qy - 18, qx + 578, qy + 578], radius=24, fill=(255, 255, 255))
    img.paste(qimg, (qx, qy))

    if len(url) <= 42:
        center(900, url, font(30), ACCENT)
    else:
        half = len(url) // 2
        center(900, url[:half], font(30), ACCENT)
        center(944, url[half:], font(30), ACCENT)
    center(1030, "دوربین گوشی را روی کد بگیرید", font(30), TXT)
    center(1084, "یا آدرس بالا را در مرورگر باز کنید", font(30), MUTED)
    d.line([120, 1150, W - 120, 1150], fill=(45, 58, 82), width=2)
    center(1176, "بدون کلید هم کار می‌کند (حالت نمایشی)", font(26), MUTED)
    center(1222, "برای هوش واقعی: کلید API را در پنل وارد کنید", font(26), MUTED)

    img.save(out)
    return True


# ───────────────────────── اصلی ─────────────────────────
def prepare_python(no_install: bool = False) -> str:
    """محیط مجازی و کتابخانه‌ها را آماده می‌کند و مسیر پایتونِ آماده را برمی‌گرداند."""
    try:
        from run_local import ensure_deps, ensure_venv  # همان منطق نصبِ اجراکننده‌ی محلی
    except Exception as e:  # noqa: BLE001
        log(f"ℹ️  آماده‌سازی خودکار ممکن نشد ({e}) — با پایتون فعلی ادامه می‌دهم.")
        return sys.executable
    try:
        py = ensure_venv()
        ensure_deps(py, install=not no_install)
        return py
    except Exception as e:  # noqa: BLE001
        log(f"⚠️  نصب کتابخانه‌ها کامل نشد ({e}) — با پایتون فعلی ادامه می‌دهم.")
        return sys.executable


def main() -> int:
    ap = argparse.ArgumentParser(description="اجرای MehranAiShabestar روی لپ‌تاپ + لینک عمومی")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--no-server", action="store_true", help="سرور را خودت بالا آورده‌ای")
    ap.add_argument("--no-qr", action="store_true")
    ap.add_argument("--no-install", action="store_true", help="کتابخانه‌ها را نصب نکن")
    ap.add_argument("--cloudflared", default=None)
    args = ap.parse_args()

    procs: list[subprocess.Popen] = []
    log("=" * 62)
    log("  MehranAiShabestar — اجرای محلی + لینک عمومی (Cloudflare Tunnel)")
    log("=" * 62)

    # ۰) آماده‌سازی پایتون/کتابخانه‌ها (بار اول چند دقیقه طول می‌کشد)
    py = prepare_python(no_install=args.no_install)

    # ۱) سرور
    if args.no_server:
        log(f"ℹ️  فرض می‌کنیم سرور روی پورت {args.port} بالاست.")
    elif port_open(args.port):
        log(f"ℹ️  پورت {args.port} از قبل باز است → سرور جدید اجرا نمی‌کنم.")
    else:
        log(f"🚀 اجرای سرور روی پورت {args.port} …")
        procs.append(subprocess.Popen([py, str(ROOT / "server.py")], cwd=str(ROOT)))

    # منتظر بالا آمدن سرور
    for _ in range(40):
        if port_open(args.port):
            break
        time.sleep(0.5)
    else:
        log("❌ سرور بالا نیامد. جدا اجرا کن:  python server.py")
        for p in procs:
            p.terminate()
        return 1
    log("✅ سرور آماده است.")

    # ۲) cloudflared
    cf = find_cloudflared(args.cloudflared)
    if cf is None:
        try:
            cf = download_cloudflared()
        except Exception as e:  # noqa: BLE001
            log(f"❌ دانلود cloudflared نشد: {e}")
            log("   دستی دانلود کن: https://github.com/cloudflare/cloudflared/releases")
            for p in procs:
                p.terminate()
            return 1

    cmd = [str(cf), "tunnel", "--url", f"http://localhost:{args.port}", "--no-autoupdate"]
    log("🌐 ساخت تونل عمومی …")
    tun = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    procs.append(tun)

    url = ""
    deadline = time.time() + 45
    assert tun.stdout is not None
    while time.time() < deadline:
        line = tun.stdout.readline()
        if not line:
            if tun.poll() is not None:
                break
            continue
        m = URL_RE.search(line)
        if m:
            url = m.group(0)
            break

    if not url:
        log("❌ لینک عمومی ساخته نشد. متن تونل را ببین:")
        for p in procs:
            p.terminate()
        return 1

    log("")
    log("  ✅ لینک عمومی برنامه‌ی تو:")
    log("")
    log(f"     {url}")
    log("")
    ip = lan_ip()
    if ip:
        log(f"  📶 در همان وای‌فای (بدون اینترنت/VPN):  http://{ip}:{args.port}")
    if not args.no_qr:
        out = ROOT / "cloud_qr.png"
        made = False
        try:  # پوستر با پایتونِ آماده‌شده ساخته می‌شود (qrcode/Pillow داخل .venv)
            r = subprocess.run([py, str(ROOT / "make_qr.py"), url, str(out)],
                               cwd=str(ROOT), capture_output=True, text=True, timeout=120)
            made = r.returncode == 0 and out.exists()
        except Exception:  # noqa: BLE001
            made = False
        if not made:
            made = make_qr(url, out)
        if made:
            log(f"  📱 پوستر QR: {out}")
    log("")
    log("  برای بستن: Ctrl+C  (تا وقتی لپ‌تاپ روشن است لینک زنده می‌ماند)")
    log("=" * 62)

    try:
        tun.wait()
    except KeyboardInterrupt:
        log("\n⏹  بستن …")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
