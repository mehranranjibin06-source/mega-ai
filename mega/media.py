"""
MEGA-AI  |  کارخانه‌ی محتوا (صدا، تصویر، ویدیو، تبلیغ)
================================================================
ساخت واقعی فایل‌های رسانه‌ای: صداگذاری فارسی (edge-tts)، تصویرسازی (PIL + فونت فارسی)،
ویدیو با زیرنویس سوخته و حرکت نرم (ffmpeg)، تبلیغ چندصحنه‌ای، و تبدیل گفتار به متن.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import textwrap
import time
from pathlib import Path
from typing import Any, Optional

from .config import ROOT, WORKSPACE

FONTS = ROOT / "assets" / "fonts"
FONT_BOLD = FONTS / "Vazirmatn-Bold.ttf"
FONT_REG = FONTS / "Vazirmatn-Regular.ttf"
def _resolve_ff(name: str) -> str:
    """ffmpeg/ffprobe را هر بار پیدا می‌کند (اگر بعد از اجرا نصب شود هم دیده می‌شود)."""
    w = shutil.which(name)
    if w:
        return w
    d = os.environ.get("MEGA_FFMPEG_DIR")
    cands = [Path(d)] if d else []
    cands.append(Path.home() / ".mega" / "ffmpeg")
    for base in cands:
        try:
            if base.is_file() and base.stem.lower() == name:
                return str(base)
            if base.is_dir():
                hits = sorted(list(base.rglob(name + ".exe")) + list(base.rglob(name)))
                if hits:
                    return str(hits[0])
        except Exception:  # noqa: BLE001
            continue
    return name


def refresh_paths() -> None:
    global FFMPEG, FFPROBE
    FFMPEG = _resolve_ff("ffmpeg")
    FFPROBE = _resolve_ff("ffprobe")


refresh_paths()

VOICES = {"زن (دیلارا)": "fa-IR-DilaraNeural", "مرد (فرید)": "fa-IR-FaridNeural",
          "انگلیسی زن": "en-US-AriaNeural", "انگلیسی مرد": "en-US-GuyNeural",
          "عربی": "ar-EG-SalmaNeural", "ترکی": "tr-TR-EmelNeural"}

THEMES = {
    "بنفش شب": ("#0b1020", "#1b2549", "#7c5cff", "#22d3ee"),
    "اقیانوس": ("#041726", "#0a2f45", "#0ea5e9", "#67e8f9"),
    "غروب": ("#1a0b1f", "#3b1035", "#f97316", "#fbbf24"),
    "جنگل": ("#04180f", "#0b3222", "#22c55e", "#a3e635"),
    "طلایی لوکس": ("#14100a", "#2b2113", "#d4af37", "#f5e6a8"),
    "قرمز آتشین": ("#1a0505", "#3a0d0d", "#ef4444", "#fb923c"),
    "سفید مینیمال": ("#f7f8fc", "#e6e9f5", "#1f2937", "#6b7280"),
}


# ------------------------------------------------------------------ کمکی‌ها
def have_ffmpeg() -> bool:
    refresh_paths()
    try:
        subprocess.run([FFMPEG, "-version"], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def probe_duration(path: str | Path) -> float:
    try:
        out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", str(path)],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


# اگر Pillow با libraqm ساخته شده باشد، خودش شکل‌دهی حروف + راست‌به‌چپ را انجام می‌دهد
# (در این حالت نباید دوباره reshaper/bidi بزنیم، وگرنه متن آینه‌ای می‌شود).
try:
    from PIL import features as _pil_features
    _RAQM = bool(_pil_features.check("raqm"))
except Exception:                                     # pragma: no cover
    _RAQM = False

_ARABIC_RE = re.compile(r"[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


THEME_EN = {
    "بنفش شب": "deep purple night, neon glow",
    "اقیانوس": "deep blue ocean, water reflections",
    "غروب": "orange sunset sky, warm light",
    "جنگل": "dark green forest, natural light",
    "طلایی لوکس": "black and gold luxury, elegant gold light",
    "قرمز آتشین": "fiery red and orange, dramatic light",
    "سفید مینیمال": "clean minimal white studio background",
}


def ai_image_enabled() -> bool:
    """آیا کلید Cloudflare داریم که بتوانیم عکس واقعی بسازیم؟"""
    if os.environ.get("MEGA_AI_IMAGE", "1") in ("0", "false", "no", "off"):
        return False
    return bool(os.environ.get("CLOUDFLARE_API_TOKEN") and os.environ.get("CLOUDFLARE_ACCOUNT_ID"))


def ai_background(prompt: str, out: str | Path, steps: int = 4, timeout: int = 90) -> str:
    """یک تصویر واقعی با هوش مصنوعی (Cloudflare FLUX) می‌سازد — رایگان با همان کلید.

    مسیر فایل ذخیره‌شده یا رشتهٔ خالی را برمی‌گرداند.
    """
    if not ai_image_enabled() or not (prompt or "").strip():
        return ""
    out = Path(out)
    if out.exists() and out.stat().st_size > 1000:      # کش: دوباره هزینه نکن
        return str(out)
    try:
        import base64
        import json as _json
        import urllib.request

        acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        tok = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
        url = (f"https://api.cloudflare.com/client/v4/accounts/{acc}"
               "/ai/run/@cf/black-forest-labs/flux-1-schnell")
        body = _json.dumps({"prompt": prompt.strip()[:1500], "steps": int(steps)}).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = _json.loads(r.read().decode("utf-8", "replace"))
        raw = base64.b64decode((data.get("result") or {}).get("image") or "")
        if len(raw) < 1000:
            return ""
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        return str(out)
    except Exception:  # noqa: BLE001
        return ""


def ai_bg_prompt(theme: str = "", extra: str = "") -> str:
    """پرامپت انگلیسی برای پس‌زمینه (بدون متن، تا حرف اضافه در عکس نیفتد)."""
    look = THEME_EN.get(theme, "modern dark premium")
    tail = "cinematic advertising background, premium, high detail, clean empty space for text"
    if extra:
        tail += f", {extra[:160]}"
    return (f"{look}, {tail}, no text, no words, no letters, no watermark, no logo")


def _direction(text: str) -> str | None:
    """جهت متن برای libraqm (فقط وقتی پشتیبانی می‌شود)."""
    return "rtl" if (_RAQM and _ARABIC_RE.search(text or "")) else None


def _text_w(draw, text: str, font) -> float:
    return draw.textlength(text, font=font, direction=_direction(text))


def _put_text(draw, xy, text: str, font, fill) -> None:
    draw.text(xy, text, font=font, fill=fill, direction=_direction(text))


def _shape(text: str) -> str:
    """شکل‌دهی حروف فارسی/عربی برای نمایش درست در تصویر."""
    if _RAQM:                      # Pillow مثل مرورگر خودش درست رندر می‌کند
        return text or ""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return "\n".join(get_display(arabic_reshaper.reshape(line)) if line.strip() else ""
                         for line in (text or "").split("\n"))
    except Exception:
        return text or ""


def _font(path: Path, size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:
        return ImageFont.load_default()


# ------------------------------------------------------------------ تصویر
def _hex2rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _wrap_fit(draw, text: str, font_path: Path, size: int, max_w: float,
              max_lines: int, min_size: int = 22):
    """متن را می‌شکند و فونت را کوچک می‌کند تا کامل داخل عرض بماند."""
    words = (text or "").split()
    while size >= min_size:
        f = _font(font_path, size)
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if _text_w(draw, _shape(trial), f) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) <= max_lines:
            return f, lines, size
        size = int(size * 0.9)
    return _font(font_path, min_size), [text or ""], min_size


def _cover(img, W: int, H: int):
    """تصویر را بدون کشیدگی، وسط‌چین و کامل‌کننده‌ی قاب می‌کند (cover)."""
    from PIL import Image
    r = max(W / img.width, H / img.height)
    img = img.resize((max(1, int(img.width * r + .5)), max(1, int(img.height * r + .5))))
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    return img.crop((left, top, left + W, top + H))


def make_image(path: str | Path, title: str, lines: list[str] | None = None,
               theme: str = "بنفش شب", ratio: str = "9:16", subtitle: str = "",
               footer: str = "", badge: str = "", align: str = "right",
               caption: str = "", bg: str | Path | None = None, bg_dim: float = 0.55,
               bg_blur: int = 0) -> str:
    """پوستر/اسلاید با گرادیان، هاله‌ی نوری و چیدمان دقیق متن فارسی (بدون سرریز، بدون همپوشانی).

    اگر ``bg`` (مسیر یک عکس) بدهی، همان عکس پشت متن می‌نشیند و یک پرده‌ی تیره روی آن می‌آید
    تا متن خوانا بماند — یعنی «از عکس خودم پوستر بساز».
    """
    from PIL import Image, ImageDraw, ImageFilter
    W, H = (1080, 1920) if ratio == "9:16" else (1920, 1080) if ratio == "16:9" else (1080, 1080)
    scale = min(W, H) / 1080 if ratio != "9:16" else 1
    c1, c2, accent, accent2 = THEMES.get(theme, THEMES["بنفش شب"])
    photo_used = False
    if not bg and ai_image_enabled():
        # پس‌زمینه‌ی واقعی با هوش مصنوعی (اگر کلید رایگان Cloudflare موجود باشد)
        bg = ai_background(ai_bg_prompt(theme), Path(path).with_suffix(".bg.jpg")) or None
    if bg:
        try:
            from PIL import Image as _I, ImageFilter as _F, ImageEnhance as _E
            ph = _I.open(str(bg))
            ph = ph.convert("RGB")
            ph = _cover(ph, W, H)
            if bg_blur:
                ph = ph.filter(_F.GaussianBlur(bg_blur))
            ph = _E.Brightness(ph).enhance(1.02)
            base = ph.copy()
            d = ImageDraw.Draw(base, "RGBA")
            r1, g1, b1 = _hex2rgb(c1)
            r2, g2, b2 = _hex2rgb(c2)
            for y in range(H):                           # پرده‌ی تیره/رنگی روی عکس
                t = y / max(H - 1, 1)
                a = int(255 * (bg_dim * (0.55 + 0.45 * t)))
                d.line([(0, y), (W, y)], fill=(int(r1 * .35), int(g1 * .35), int(b1 * .45), a))
            photo_used = True
        except Exception:
            photo_used = False
    if not photo_used:
        base = Image.new("RGB", (W, H), _hex2rgb(c1))
        d = ImageDraw.Draw(base, "RGBA")
        r1, g1, b1 = _hex2rgb(c1)
        r2, g2, b2 = _hex2rgb(c2)
        for y in range(H):                               # گرادیان عمودی
            t = y / max(H - 1, 1)
            d.line([(0, y), (W, y)], fill=(int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t),
                                           int(b1 + (b2 - b1) * t)))
    glow = Image.new("RGB", (W, H), (0, 0, 0))           # هاله‌های نوری رنگی
    gd = ImageDraw.Draw(glow, "RGBA")
    for fx, fy, rad, col, alpha in [(0.14, 0.16, 0.44, accent, 80), (0.88, 0.30, 0.36, accent2, 70),
                                    (0.28, 0.88, 0.42, accent, 70)]:
        rr = int(min(W, H) * rad)
        gd.ellipse([W * fx - rr, H * fy - rr, W * fx + rr, H * fy + rr],
                   fill=_hex2rgb(col) + (alpha,))
    glow = glow.filter(ImageFilter.GaussianBlur(int(min(W, H) * 0.11)))
    if photo_used:                                    # روی عکس، هاله ملایم‌تر
        base = Image.blend(base, glow, 0.22)
    else:
        base = Image.blend(base, Image.blend(base, glow, 0.5), 0.6)
    img = base
    d = ImageDraw.Draw(img, "RGBA")

    pad = int(W * 0.075)
    inner_w = W - 2 * pad - int(W * 0.03)
    size_title = int(W * 0.085 * (1 if ratio == "9:16" else 0.72))
    size_sub = int(size_title * 0.56)
    size_li = int(size_title * 0.50)
    size_badge = int(size_title * 0.42)

    # ── چیدمان: اول همه را اندازه می‌گیریم، بعد کادر را به اندازه‌ی محتوا می‌کشیم
    t_font, t_lines, t_size = _wrap_fit(d, title, FONT_BOLD, size_title, inner_w, 3)
    s_font, s_lines, s_size = _wrap_fit(d, subtitle, FONT_REG, size_sub, inner_w, 3) if subtitle else (None, [], 0)
    li_items = []
    for ln in (lines or [])[:6]:
        f, ls, _ = _wrap_fit(d, str(ln), FONT_REG, size_li, inner_w, 2)
        li_items.append((f, ls))
    gap = int(W * 0.022)
    total = (t_size * 1.34 * len(t_lines) + (int(t_size * 0.34) if badge else 0)
             + (s_size * 1.45 * len(s_lines) if s_lines else 0)
             + sum(len(ls) * size_li * 1.5 for _, ls in li_items)
             + gap * (bool(badge) + bool(t_lines) + bool(s_lines) + bool(li_items) + 1))
    box_h = min(int(total + W * 0.07), int(H * 0.80))
    box_top = (H - box_h) // 2
    d.rounded_rectangle([pad, box_top, W - pad, box_top + box_h], radius=int(W * 0.045),
                        fill=(0, 0, 0, 105), outline=(255, 255, 255, 30), width=3)

    def draw_line(text: str, font, size: int, color: str, y: float, x_right: float) -> float:
        t = _shape(text)
        tw = _text_w(d, t, font)
        x = (W - tw) / 2 if align == "center" else x_right - tw
        _put_text(d, (x, y), t, font, color)
        return y + size * 1.34

    y = box_top + int(W * 0.055)
    right = W - pad - int(W * 0.022)
    if badge:
        f = _font(FONT_BOLD, size_badge)
        t = _shape(badge)
        tw = _text_w(d, t, f)
        d.rounded_rectangle([right - tw - 34, y - 6, right + 6, y + size_badge * 1.62],
                            radius=999, fill=_hex2rgb(accent) + (230,))
        _put_text(d, (right - tw - 14, y + 2), t, f, "#ffffff")
        y += size_badge * 1.62 + gap
    for ln in t_lines:
        y = draw_line(ln, t_font, t_size, "#ffffff", y, right)
    if s_lines:
        y += int(gap * 0.6)
        for ln in s_lines:
            y = draw_line(ln, s_font, s_size, accent2, y, right)
    if li_items:
        y += int(gap * 0.8)
        indent = int(size_li * 0.62)
        for f, ls in li_items:
            for j, ln in enumerate(ls):
                t = _shape(ln)
                tw = _text_w(d, t, f)
                x = (W - tw) / 2 if align == "center" else (right - indent) - tw
                _put_text(d, (x, y), t, f, "#e8ecff")
                if j == 0:                       # گلوله‌ی سمت راست (شروع خط در RTL)
                    r = int(size_li * 0.13)
                    cx, cy = right - r, y + size_li * 0.62
                    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_hex2rgb(accent2))
                y += size_li * 1.34

    # ── زیرنویس سوخته (پایین قاب) — با PIL، پس فارسی/عربی درست شکل می‌گیرد
    if caption:
        cap_size = int(size_li * 0.95)
        c_font, c_lines, c_size = _wrap_fit(d, caption, FONT_BOLD, cap_size, W - 2 * int(W * 0.13), 3,
                                            min_size=int(cap_size * 0.72))
        line_h = c_size * 1.45
        band_h = int(line_h * len(c_lines) + W * 0.055)
        band_bottom = H - int(H * 0.035)
        band_top = band_bottom - band_h
        d.rounded_rectangle([int(W * 0.06), band_top, W - int(W * 0.06), band_bottom],
                            radius=int(W * 0.022), fill=(0, 0, 0, 165))
        cy = band_top + W * 0.026
        for ln in c_lines:
            t = _shape(ln)
            tw = _text_w(d, t, c_font)
            _put_text(d, ((W - tw) / 2, cy), t, c_font, "#ffffff")
            cy += line_h

    if footer:
        f = _font(FONT_REG, int(size_li * 0.86))
        t = _shape(footer)
        tw = _text_w(d, t, f)
        _put_text(d, ((W - tw) / 2, box_top + box_h + int(W * 0.035)), t, f, "#cbd5ffbb")
    d.rectangle([0, H - 14, W, H], fill=_hex2rgb(accent))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
    return str(path)


# ------------------------------------------------------------------ صدا
async def tts(text: str, out: str | Path, voice: str = "fa-IR-DilaraNeural",
              rate: str = "+0%", pitch: str = "+0Hz") -> dict:
    """گفتار از متن (edge-tts). اگر شبکه نبود، سکوت هم‌اندازه تولید می‌شود."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = (text or "").strip()
    if not text:
        text = "…"
    try:
        import edge_tts
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await comm.save(str(out))
        if out.exists() and out.stat().st_size > 1200:
            return {"ok": True, "path": str(out), "seconds": round(probe_duration(out), 2),
                    "engine": "edge-tts", "voice": voice}
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        try:
            from gtts import gTTS
            gTTS(text=text, lang="fa").save(str(out))
            return {"ok": True, "path": str(out), "seconds": round(probe_duration(out), 2),
                    "engine": "gTTS", "note": f"edge-tts ناموفق ({err})"}
        except Exception:
            pass
        # واپسین چاره: سکوت
        secs = max(2.0, len(text) / 14)
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{secs:.2f}",
                        "-q:a", "9", str(out)], capture_output=True, timeout=120)
        return {"ok": True, "path": str(out), "seconds": round(secs, 2), "engine": "silent",
                "note": f"صداگذاری ناموفق بود ({err})؛ فایل سکوت ساخته شد"}
    return {"ok": False, "error": "تولید صدا ناموفق بود"}


async def stt(path: str | Path, language: str = "fa") -> dict:
    """گفتار به متن: اول Whisper API (اگر کلید باشد)، بعد مدل محلی، بعد خطا."""
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "فایل صوتی پیدا نشد"}
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if key:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=180) as c:
                with open(p, "rb") as f:
                    r = await c.post("https://api.openai.com/v1/audio/transcriptions",
                                     headers={"Authorization": f"Bearer {key}"},
                                     files={"file": (p.name, f, "audio/mpeg")},
                                     data={"model": "whisper-1", "language": language})
            if r.status_code == 200:
                return {"ok": True, "text": r.json().get("text", ""), "engine": "whisper-api"}
            return {"ok": False, "error": f"Whisper API: HTTP {r.status_code} {r.text[:200]}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Whisper API: {e}"}
    try:
        from faster_whisper import WhisperModel  # نوع: ignore
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(p), language=language)
        return {"ok": True, "text": " ".join(s.text.strip() for s in segments), "engine": "faster-whisper"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"موتور تشخیص گفتار در دسترس نیست ({e}). "
                                     f"یا OPENAI_API_KEY بده یا: pip install faster-whisper"}


# ------------------------------------------------------------------ ویدیو
def _srt_time(t: float) -> str:
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s - int(s)) * 1000):03d}"


def write_srt(segments: list[tuple[float, float, str]], path: str | Path) -> str:
    lines = []
    for i, (a, b, txt) in enumerate(segments, 1):
        lines += [str(i), f"{_srt_time(a)} --> {_srt_time(b)}", txt.strip(), ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return str(path)


async def make_video(scenes: list[dict], out: str | Path, ratio: str = "9:16",
                     theme: str = "بنفش شب", voice: str = "fa-IR-DilaraNeural",
                     subtitles: bool = True, music: bool = False, fps: int = 30,
                     motion: bool = True, brand: str = "",
                     bg_image: str | Path | None = None, photo_scenes: str = "all") -> dict:
    """
    ساخت ویدیو از صحنه‌ها.
    هر صحنه: {title, text, lines, audio(متن گویندگی), seconds, image(مسیر تصویر آماده), theme}
    """
    if not have_ffmpeg():
        return {"ok": False, "error": "ffmpeg نصب نیست"}
    out = Path(out)
    work = out.parent / (out.stem + "_parts")
    work.mkdir(parents=True, exist_ok=True)
    w, h = (1080, 1920) if ratio == "9:16" else (1920, 1080)
    clips, srt_segments, cursor = [], [], 0.0

    for i, sc in enumerate(scenes, 1):
        img = Path(sc.get("image") or work / f"scene{i}.png")
        cap = (sc.get("text") or sc.get("subtitle") or "").strip() if subtitles else ""
        if not sc.get("image"):
            use_bg = None
            if bg_image and (photo_scenes == "all" or (photo_scenes == "hook" and i == 1)):
                use_bg = Path(sc.get("bg") or bg_image)
            make_image(img, sc.get("title", ""), sc.get("lines"),
                       theme=sc.get("theme", theme), ratio=ratio,
                       subtitle=sc.get("subtitle", ""), badge=sc.get("badge", ""),
                       footer=brand or sc.get("footer", ""), caption=cap, bg=use_bg)
        narration = (sc.get("audio") or sc.get("text") or sc.get("title") or "").strip()
        audio = work / f"scene{i}.mp3"
        tts_res = await tts(narration, audio, voice=voice)
        secs = float(sc.get("seconds") or 0) or (tts_res.get("seconds", 3.0) + 0.45)
        secs = max(1.6, min(secs, 90))
        clip = work / f"clip{i}.mp4"
        vf = (f"scale={int(w*1.08)}:{int(h*1.08)},zoompan=z='min(zoom+0.00045,1.10)':"
              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(secs*fps)}:s={w}x{h},"
              f"fps={fps},format=yuv420p") if motion else f"scale={w}:{h},fps={fps},format=yuv420p"
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", str(img),
               "-i", str(tts_res["path"]), "-t", f"{secs:.2f}",
               "-filter_complex", f"[0:v]{vf}[v]",
               "-map", "[v]", "-map", "1:a",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-shortest", str(clip)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode != 0 or not clip.exists():
            return {"ok": False, "error": f"ساخت صحنه‌ی {i} ناموفق: {r.stderr[-300:]}"}
        clips.append(clip)
        text = (sc.get("text") or narration).strip()
        if text:
            srt_segments.append((cursor + 0.2, cursor + min(secs - 0.1, 6.5), text))
        cursor += secs

    # چسباندن صحنه‌ها
    lst = work / "list.txt"
    lst.write_text("\n".join(f"file '{c.name}'" for c in clips), encoding="utf-8")
    merged = work / "merged.mp4"
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
                        "-safe", "0", "-i", str(lst), "-c", "copy", str(merged)],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        return {"ok": False, "error": f"چسباندن صحنه‌ها ناموفق: {r.stderr[-300:]}"}

    video = merged
    if subtitles and srt_segments:
        srt_file = write_srt(srt_segments, work / "subs.srt")   # نسخه‌ی قابل ویرایش
        try:
            shutil.copy(srt_file, out.with_suffix(".srt"))       # کنار خروجی نهایی هم باشد
        except Exception:
            pass

    # موسیقی پس‌زمینه‌ی ملایم (تولیدشده)
    if music:
        bed = work / "music.m4a"
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", f"sine=frequency=196:duration={cursor:.2f}",
                        "-af", "tremolo=f=0.4:d=0.35,volume=0.06,aformat=channel_layouts=stereo",
                        "-c:a", "aac", str(bed)], capture_output=True, timeout=300)
        withmus = work / "withmusic.mp4"
        r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                            "-i", str(bed), "-filter_complex",
                            "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0[a]",
                            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                            str(withmus)], capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and withmus.exists():
            video = withmus

    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(video, out)
    return {"ok": True, "path": str(out), "seconds": round(probe_duration(out), 2),
            "scenes": len(scenes), "size_kb": round(out.stat().st_size / 1024),
            "ratio": ratio, "music": music}


# ------------------------------------------------------------------ تبلیغ
AD_TEMPLATE = [
    {"role": "hook", "title": "{brand}", "subtitle": "یک راه ساده‌تر هم هست",
     "audio": "اگر دنبال {brand} هستی، این را ببین."},
    {"role": "problem", "title": "مشکل کجاست؟", "lines": ["کارها طول می‌کشد", "هزینه بالا می‌رود",
                                                          "نتیجه قابل پیش‌بینی نیست"],
     "audio": "مشکل این است که کارها زمان‌بر و پرهزینه‌اند و نتیجه هم قابل پیش‌بینی نیست."},
    {"role": "solution", "title": "راه‌حل ما", "lines": ["سرعت چند برابر", "هزینه پایین‌تر",
                                                         "کیفیت حرفه‌ای"],
     "audio": "راه‌حل ما سرعت چند برابر، هزینه‌ی پایین‌تر و کیفیت حرفه‌ای است."},
    {"role": "proof", "title": "نتیجه", "lines": ["آماده در چند دقیقه", "قابل استفاده‌ی فوری",
                                                   "بدون دانش فنی"],
     "audio": "نتیجه در چند دقیقه آماده می‌شود و همان لحظه قابل استفاده است."},
    {"role": "cta", "title": "همین حالا شروع کن", "subtitle": "لینک زیر را بزن",
     "audio": "همین حالا شروع کن. لینک در توضیحات است."},
]


_AD_EXACT_STOP = {"یک", "یه", "و", "با", "برای", "را", "از", "در", "به", "کن", "کنید", "کنم",
                  "من", "ما", "کوتاه", "بلند", "مورد", "درمورد", "می‌خواهم", "میخوام",
                  "می‌خواهم.", "خواهم", "لطفا", "لطفاً", "یه", "برام", "برایم"}
_AD_STEM_STOP = ("ویدیو", "ویدئو", "کلیپ", "تبلیغ", "پوستر", "موشن", "بساز", "لطف", "دربار",
                 "ساخت", "رندر", "تولید", "آماده", "درست")


def _brand_from_topic(topic: str) -> str:
    """نام برند/موضوع را از متن خواسته‌ی کاربر بیرون می‌کشد (برای ویدیوی نمونه و پیش‌فرض)."""
    words = [w for w in re.split(r"[\s،,.:;!?\"']+", (topic or "").strip()) if w.strip()]
    keep = [w for w in words
            if "#" not in w and "گفت‌وگو" not in w and "خواسته" not in w
            and w not in _AD_EXACT_STOP and not any(w.startswith(st) for st in _AD_STEM_STOP)]
    name = " ".join(keep).strip(" .،-")
    return name[:26] if name else ""


async def make_ad(topic: str, out: str | Path, ratio: str = "9:16", theme: str = "طلایی لوکس",
                  voice: str = "fa-IR-FaridNeural", brand: str = "", music: bool = True,
                  script: Optional[list[dict]] = None, image: str | Path | None = None,
                  photo_scenes: str = "all") -> dict:
    """ساخت تبلیغ ویدیویی چندصحنه‌ای (قلاب → مشکل → راه‌حل → اثبات → فراخوان)."""
    brand = (brand or "").strip()
    if not brand or brand in ("برند تو", "برند شما", "برند"):
        brand = _brand_from_topic(topic) or "برند تو"
    scenes = []
    for i, sc in enumerate(script or AD_TEMPLATE):
        scenes.append({
            "title": (sc.get("title") or "").format(topic=topic, brand=brand),
            "subtitle": (sc.get("subtitle") or "").format(topic=topic, brand=brand),
            "lines": sc.get("lines"),
            "audio": (sc.get("audio") or sc.get("text") or "").format(topic=topic, brand=brand),
            "theme": sc.get("theme") or (theme if i % 2 == 0 else "بنفش شب"),
            "badge": brand,
        })
        if sc.get("role") == "cta" and brand and "{brand}" not in (sc.get("title") or ""):
            scenes[-1]["title"] = f"همین حالا {brand} را امتحان کن"   # فقط برای قالب‌های دلخواه
    res = await make_video(scenes, out, ratio=ratio, theme=theme, voice=voice,
                           subtitles=True, music=music, brand=brand, motion=True,
                           bg_image=image, photo_scenes=photo_scenes)
    if res.get("ok"):
        res["kind"] = "ad"
        res["topic"] = topic
    return res


def poster_from_photo(photo: str | Path, out: str | Path, title: str = "", lines: list[str] | None = None,
                      subtitle: str = "", badge: str = "", footer: str = "", caption: str = "",
                      ratio: str = "9:16", theme: str = "بنفش شب", dim: float = 0.55) -> dict:
    """پوستر واقعی از عکس خودِ کاربر: برش هوشمند به نسبت دلخواه + پرده‌ی تیره + چیدمان فارسی."""
    from PIL import Image
    ph = Path(photo)
    if not ph.is_file():
        return {"ok": False, "error": f"عکس پیدا نشد: {ph}"}
    try:
        img = Image.open(ph)
        w, h = img.size
        img.close()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"عکس خوانده نشد: {e}"}
    info = {"photo": ph.name, "photo_size": f"{w}×{h}"}
    path = make_image(out, title, lines, theme=theme, ratio=ratio, subtitle=subtitle,
                      badge=badge, footer=footer, caption=caption, bg=ph, bg_dim=dim)
    info.update({"ok": True, "path": str(path), "ratio": ratio})
    return info
