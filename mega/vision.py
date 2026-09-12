"""
دیدن تصویر — واقعی.
۱) تحلیل فنی محلی (بدون هیچ کلیدی کار می‌کند): ابعاد، رنگ‌ها، روشنایی، وضوح، پیشنهاد برش.
۲) توصیف/تحلیل با مدل بینایی (وقتی کلید هست): تصویر را base64 می‌فرستیم به مدل‌های
   چندوجهی (GPT-4o / Gemini / Claude / Qwen-VL …) از همان گیت‌وی‌هایی که کاربر وصل کرده.
"""
from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path

# مدل‌های شناخته‌شده‌ی چندوجهی (به ترتیب اولویت) — نام‌ها با جست‌وجوی جزئی پیدا می‌شوند
VISION_HINTS = ["gpt-4o", "gpt-4.1", "gpt-5", "gemini-2.5-pro", "gemini-2.5-flash",
                "gemini-2.0-flash", "claude-sonnet-4-5", "claude-3-7", "claude-3-5-sonnet",
                "qwen-vl-max", "qwen2.5-vl", "llama-3.2-90b-vision", "llama-3.2-11b-vision",
                "grok-2-vision", "moonshot-v1-8k-vision", "glm-4v"]

MAX_SIDE = 1280          # برای کم‌کردن حجم ارسال، تصویر بزرگ کوچک می‌شود
MAX_BYTES = 3_500_000


def _shrink(path: Path) -> tuple[bytes, str]:
    """تصویر را برای ارسال آماده می‌کند (کوچک‌سازی + تبدیل به JPEG)."""
    from PIL import Image
    img = Image.open(path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, MAX_SIDE / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
    import io
    for quality in (88, 74, 60):
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= MAX_BYTES:
            return data, "image/jpeg"
    return data, "image/jpeg"


def _data_url(path: Path) -> str:
    try:
        data, mime = _shrink(path)
    except Exception:
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _vision_specs():
    """پرووایدرهای دارای کلید + مدل‌هایی که احتمالاً بینایی دارند."""
    from .config import PROVIDERS
    ranked: list[tuple[int, str, list[str]]] = []
    for pid, p in PROVIDERS.items():
        if not p.key:
            continue
        prefs = []
        for m in list(p.default_models) + VISION_HINTS:
            if any(h in (m or "").lower() for h in VISION_HINTS) or any(
                    h in (m or "").lower() for h in ("vision", "-vl", "vl-")):
                if m not in prefs:
                    prefs.append(m)
        prefs += [m for m in VISION_HINTS if m not in prefs]
        ranked.append((0 if p.iran_friendly else 1, pid, prefs))
    ranked.sort(key=lambda t: t[0])
    return [(pid, prefs) for _, pid, prefs in ranked]


async def model_vision(path: str | Path, question: str = "", settings=None,
                       prompts_extra: str = "") -> dict:
    """توصیف و تحلیل تصویر با مدل چندوجهی (اولین پرووایدری که جواب بدهد)."""
    from .providers import _pick_from_provider, chat, ModelSpec   # noqa: PLC2701
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": "فایل تصویر پیدا نشد"}
    url = await __import__("asyncio").to_thread(_data_url, p)
    specs = _vision_specs()
    if not specs:
        return {"ok": False, "hint": "کلید API نداری؛ تحلیل فنی محلی انجام شد. برای توصیف هوشمند "
                                     "تصویر یک کلید (گیت‌وی ایرانی هم کافی است) وصل کن."}
    ask = question.strip() or "این تصویر را دقیق توصیف کن."
    sys_msg = ("تو یک کارشناس بینایی ماشین و تبلیغات هستی. تصویر را دقیق و بی‌اغراق توصیف کن: "
               "چه چیزی دیده می‌شود، فضای کلی، رنگ‌ها، کیفیت، چه متنی روی تصویر هست، "
               "و چه استفاده‌ای از آن می‌شود (تبلیغ، پوستر، پروفایل…). فارسی و ساخت‌یافته بنویس.")
    last_err = ""
    for pid, prefs in specs:
        try:
            models = await _pick_from_provider(pid, prefs, set(), how_many=2, tier="max")
        except Exception:
            models = []
        for model in (models or prefs[:1]):
            spec = ModelSpec(pid, model, role="vision", temperature=0.3, max_tokens=1200)
            messages = [
                {"role": "system", "content": sys_msg + (f"\n{prompts_extra}" if prompts_extra else "")},
                {"role": "user", "content": [
                    {"type": "text", "text": ask},
                    {"type": "image_url", "image_url": {"url": url}},
                ]},
            ]
            res = await chat(spec, messages, settings=settings)
            if res.ok and res.text.strip() and not res.demo:
                return {"ok": True, "text": res.text.strip(), "model": f"{pid}:{model}",
                        "provider": pid, "seconds": res.seconds}
            last_err = res.error or last_err
    hint = "مدل بینایی جواب نداد (شاید این مدل‌ها روی کلیدت فعال نیستند)."
    if "401" in last_err or "کاربری" in last_err:
        hint = "کلید رد شد؛ کلید را در ⚙️ تنظیمات دوباره تست کن."
    return {"ok": False, "error": last_err, "hint": hint}


async def describe_image(path: str | Path, question: str = "", settings=None,
                         use_model: bool = True) -> dict:
    """هم تحلیل فنی محلی و هم (اگر بشود) توصیف با مدل."""
    from .analyze import analyze_image_local
    p = Path(path)
    local = analyze_image_local(p)
    out: dict = {"ok": True, "local": local, "model_text": "", "model": ""}
    demo = False
    try:
        from .demo_model import BRIDGE
        demo = bool(BRIDGE.get("active"))
    except Exception:
        pass
    if use_model and not demo:
        res = await model_vision(p, question=question, settings=settings)
        if res.get("ok"):
            out["model_text"] = res["text"]
            out["model"] = res.get("model", "")
        else:
            out["hint"] = res.get("hint") or res.get("error") or ""
    elif demo:
        out["hint"] = ("حالت نمایشی روشن است (کلیدی وصل نیست) → تحلیل فنی واقعی تصویر بالا آمده. "
                       "برای توصیف هوشمند تصویر، از ⚙️ یک کلید وصل کن.")
    # پیشنهاد کپی تبلیغاتی بر اساس یافته‌های محلی
    out["suggestion"] = _ad_suggestion(local, question)
    return out


def _ad_suggestion(local: dict, question: str) -> str:
    """یک پیشنهاد عملی برای استفاده از تصویر (بدون مدل)."""
    lines = []
    if local.get("orientation") == "عمودی":
        lines.append("این تصویر عمودی است → مناسب استوری/ریلز ۹:۱۶ ✅")
    elif local.get("orientation") == "افقی":
        lines.append("این تصویر افقی است → مناسب پوستر ۱۶:۹ و بنر سایت ✅")
    else:
        lines.append("این تصویر مربعی است → مناسب پست ۱:۱ اینستاگرام ✅")
    if (local.get("brightness") or 0) < 90:
        lines.append("تصویر تاریک است؛ برای متن روی آن، نوار نیمه‌شفاف اضافه می‌کنیم.")
    if (local.get("sharpness") or 0) < 9:
        lines.append("تصویر کمی نرم است؛ متن را بزرگ‌تر و کم‌تر می‌گذاریم.")
    lines.append("می‌توانی بگویی «از همین عکس پوستر بساز» یا «از این عکس تبلیغ ویدیویی بساز».")
    return " ".join(lines)
