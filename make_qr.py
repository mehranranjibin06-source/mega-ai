# -*- coding: utf-8 -*-
"""پوستر QR برای لینک عمومی برنامه (MehranAiShabestar).

استفاده:  python3 make_qr.py https://xxxx.trycloudflare.com [خروجی.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT_BOLD = ROOT / "assets" / "fonts" / "Vazirmatn-Bold.ttf"
FONT_REG = ROOT / "assets" / "fonts" / "Vazirmatn-Regular.ttf"
LOGO = ROOT / "assets" / "logo_icon.png"

BRAND = "MehranAiShabestar"
FA = "مهران‌هوش شبستر"

W, H = 1000, 1460
BG, CARD, ACCENT, TXT, MUTED = (13, 17, 28), (24, 31, 46), (86, 156, 255), (235, 240, 248), (150, 163, 184)

# چیدمان (از بالا به پایین)
LOGO_SIZE, LOGO_Y = 200, 66
TITLE_Y = 300
SUB_Y = 384
QR_SIZE, QR_Y = 560, 452
URL_Y = 1072
NOTE1_Y = 1188
NOTE2_Y = 1236
LINE_Y = 1296
FOOT1_Y = 1320
FOOT2_Y = 1366


def font(path: Path, size: int):
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return ImageFont.load_default()


def build(url: str, out: str | Path) -> Path:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([40, 40, W - 40, H - 40], radius=36, fill=CARD, outline=(45, 58, 82), width=3)

    f_title = font(FONT_BOLD, 54)
    f_sub = font(FONT_REG, 31)
    f_url = font(FONT_BOLD, 30)
    f_note = font(FONT_REG, 30)
    f_foot = font(FONT_REG, 26)

    def center(y: int, text: str, f, fill) -> None:
        d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)

    # ── لوگو
    if LOGO.exists():
        try:
            lg = Image.open(LOGO).convert("RGB").resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS)
            lx = (W - LOGO_SIZE) // 2
            d.rounded_rectangle([lx - 8, LOGO_Y - 8, lx + LOGO_SIZE + 8, LOGO_Y + LOGO_SIZE + 8],
                                radius=30, fill=(255, 255, 255))
            img.paste(lg, (lx, LOGO_Y))
        except Exception:
            pass

    # ── برند
    center(TITLE_Y, BRAND, f_title, TXT)
    center(SUB_Y, f"{FA} — هوش مصنوعی شخصی", f_sub, MUTED)

    # ── QR
    qr = qrcode.QRCode(box_size=10, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qimg = qimg.resize((QR_SIZE, QR_SIZE), Image.NEAREST)
    qx = (W - QR_SIZE) // 2
    d.rounded_rectangle([qx - 18, QR_Y - 18, qx + QR_SIZE + 18, QR_Y + QR_SIZE + 18],
                        radius=24, fill=(255, 255, 255))
    img.paste(qimg, (qx, QR_Y))

    # ── آدرس
    if len(url) <= 42:
        center(URL_Y, url, f_url, ACCENT)
    else:
        half = len(url) // 2
        center(URL_Y, url[:half], f_url, ACCENT)
        center(URL_Y + 44, url[half:], f_url, ACCENT)

    center(NOTE1_Y, "دوربین گوشی را روی کد بگیرید", f_note, TXT)
    center(NOTE2_Y, "یا آدرس بالا را در مرورگر باز کنید", f_note, MUTED)

    d.line([120, LINE_Y, W - 120, LINE_Y], fill=(45, 58, 82), width=2)
    center(FOOT1_Y, "بدون کلید هم کار می‌کند (حالت نمایشی)", f_foot, MUTED)
    center(FOOT2_Y, "برای هوش واقعی: کلید API را در پنل وارد کنید", f_foot, MUTED)

    out = Path(out)
    img.save(out)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    target = build(sys.argv[1].strip(),
                   sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "cloud_qr.png"))
    print("saved:", target)
