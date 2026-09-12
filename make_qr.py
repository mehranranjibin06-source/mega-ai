# -*- coding: utf-8 -*-
"""پوستر QR برای لینک عمومی برنامه (ابرهوش).
استفاده:  python3 make_qr.py https://xxxx.trycloudflare.com [خروجی.png]
نکته: فونت وزیرمتن از assets/fonts خوانده می‌شود؛ برای متن فارسی نیاز به libraqm است
(در این پروژه رِشِیپینگ غیرفعال است و فونت خودش حروف را درست می‌چیند).
"""
import sys
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT_BOLD = ROOT / "assets" / "fonts" / "Vazirmatn-Bold.ttf"
FONT_REG = ROOT / "assets" / "fonts" / "Vazirmatn-Regular.ttf"

W, H = 1000, 1300
BG = (13, 17, 28)
CARD = (24, 31, 46)
ACCENT = (86, 156, 255)
TXT = (235, 240, 248)
MUTED = (150, 163, 184)


def font(path, size):
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return ImageFont.load_default()


def rtl(text):
    """فقط برای اطمینان: متن باید از قبل منطقی باشد؛ اینجا خطوط کوتاه دستی چیده شده‌اند."""
    return text


def center(d, y, text, f, fill):
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y), text, font=f, fill=fill)
    return w


def build(url, out):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # کارت اصلی
    d.rounded_rectangle([40, 40, W - 40, H - 40], radius=36, fill=CARD, outline=(45, 58, 82), width=3)

    f_title = font(FONT_BOLD, 64)
    f_sub = font(FONT_REG, 34)
    f_url = font(FONT_BOLD, 30)
    f_note = font(FONT_REG, 30)
    f_foot = font(FONT_REG, 26)

    center(d, 92, "ابرهوش", f_title, TXT)
    center(d, 178, "برنامه‌ی هوش مصنوعی شما", f_sub, MUTED)

    # QR
    qr = qrcode.QRCode(version=None, box_size=10, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    qimg = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qimg = qimg.resize((560, 560), Image.NEAREST)
    qx, qy = (W - 560) // 2, 268
    d.rounded_rectangle([qx - 18, qy - 18, qx + 560 + 18, qy + 560 + 18], radius=24, fill=(255, 255, 255))
    img.paste(qimg, (qx, qy))

    # URL (دو تکه تا از کارت بیرون نزند)
    y = 900
    if len(url) <= 42:
        center(d, y, url, f_url, ACCENT)
    else:
        head, tail = url[: len(url) // 2], url[len(url) // 2:]
        center(d, y, head, f_url, ACCENT)
        center(d, y + 44, tail, f_url, ACCENT)

    center(d, 1030, "دوربین گوشی را روی کد بگیرید", f_note, TXT)
    center(d, 1084, "یا آدرس بالا را در مرورگر باز کنید", f_note, MUTED)

    d.line([120, 1150, W - 120, 1150], fill=(45, 58, 82), width=2)
    center(d, 1176, "بدون کلید هم کار می‌کند (حالت نمایشی)", f_foot, MUTED)
    center(d, 1222, "برای هوش واقعی: یک کلید API را در پنل وارد کنید", f_foot, MUTED)

    img.save(out)
    print("saved:", out, img.size)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    build(sys.argv[1].strip(), sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "cloud_qr.png"))
