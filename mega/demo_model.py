"""
MEGA-AI  |  مدل نمایشی داخلی (Demo Model)
================================================================
اگر هیچ کلید API تنظیم نشده باشد، سیستم این مدل داخلی را به‌عنوان پرووایدر
«آزمایشی» بالا می‌آورد تا کل خط تولید (راهبر → پنل خبرگان → ابزار واقعی → نقد →
داوری → بازبین) بدون هیچ هزینه‌ای کار کند. به‌محض ورود اولین کلید واقعی،
این مدل کنار می‌رود و مدل‌های واقعی جایش را می‌گیرند.

به‌صورت مستقل هم قابل اجراست (برای تست پرووایدرهای واقعی):
    python -m mega.demo_model
    export OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:8123/v1
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .media import _brand_from_topic  # noqa: E402  (فقط برای نام برند در مدل نمایشی)

DEMO_MODELS = ["demo-gpt", "demo-claude", "demo-gemini", "demo-grok", "demo-deepseek", "demo-qwen"]
BRIDGE = {"active": False, "path": "/mock/v1"}

app = FastAPI(title="MEGA-AI demo model")


# ------------------------------------------------------------------ نقش‌یابی
# نشانه‌های دقیق هر نقش (از ابتدای system prompt هر نقش در orchestrator)
_ROLE_MARKS = [
    ("agent", ("«کارگزار مطلق»",)),
    ("verifier", ("«بازبین»",)),
    ("judge", ("«داور نهایی»",)),
    ("critic", ("«نقدگر»",)),
    ("router", ("«مغز راهبر»",)),
    ("expert", ("از خبرگان", "ابزارهای تو", "زاویه‌ی تخصصی")),
]


def role_of(system: str) -> str:
    s = system or ""
    for role, marks in _ROLE_MARKS:
        if any(mk in s for mk in marks):
            return role
    return "plain"


def _last_user(body: dict) -> str:
    for m in reversed(body.get("messages") or []):
        if m.get("role") == "user":
            return m.get("content") or ""
    return ""


def _panel_names(body: dict) -> list[str]:
    """نام خبره‌ها را از پاسخ‌های چسبیده در پیام داور بیرون می‌کشد."""
    txt = _last_user(body)
    found = re.findall(r"^###\s+([^\n(]+?)\s*\(([^)]+)\)\s*$", txt, re.M)
    names = [f.strip() for f, _ in found]
    return names[:8] or ["demo-gpt", "demo-claude"]


def _topic(body: dict) -> str:
    txt = _last_user(body)
    for marker in ("## درخواست فعلی کاربر", "## درخواست کاربر", "## درخواست\n", "## درخواست\n"):
        if marker in txt:
            txt = txt.split(marker, 1)[1]
            break
    for cut in ("## معیار", "## پاسخ خبرگان", "## یافته", "## گفت‌وگوی قبلی", "### پاسخ", "## نقد"):
        if cut in txt:
            txt = txt.split(cut, 1)[0]
    return re.sub(r"\s+", " ", txt).strip()[:280]


def _recipe(topic: str) -> tuple[str, str]:
    """
    برای چند نوع درخواست رایج، کد پایتونِ واقعی و مربوط می‌سازد تا مدل نمایشی
    هم مثل یک خبره‌ی واقعی «خروجی اجرایی» نشان بدهد.
    """
    t = topic.lower()
    if any(k in topic for k in ("عدد اول", "اعداد اول", "prime")) or "prime" in t:
        return (
            "def primes(n):\n"
            "    sieve = [True] * (n + 1)\n"
            "    sieve[0:2] = [False, False]\n"
            "    for i in range(2, int(n ** 0.5) + 1):\n"
            "        if sieve[i]:\n"
            "            for j in range(i * i, n + 1, i):\n"
            "                sieve[j] = False\n"
            "    return [i for i, ok in enumerate(sieve) if ok]\n\n"
            "print('اعداد اول تا ۱۰۰:', primes(100))\n"
            "print('تعدادشان:', len(primes(100)))",
            "غربال اراتوستن با پیچیدگی O(n log log n)",
        )
    if any(k in topic for k in ("فیبوناچی", "فیبوناچ", "fibonacci")) or "fib" in t:
        return (
            "def fib(n):\n"
            "    a, b, out = 0, 1, []\n"
            "    for _ in range(n):\n"
            "        out.append(a)\n"
            "        a, b = b, a + b\n"
            "    return out\n\n"
            "print('۱۵ عدد اول فیبوناچی:', fib(15))\n"
            "print('جمعشان:', sum(fib(15)))",
            "نسخه‌ی تکراری و بهینه (بدون بازگشت نمایی)",
        )
    if any(k in topic for k in ("بهره", "سود", "درصد", "قیمت", "هزینه", "مالی")):
        return (
            "principal, rate, years = 100_000_000, 0.25, 5   # تومان، ۲۵٪، ۵ سال\n"
            "simple = principal * (1 + rate * years)\n"
            "compound = principal * (1 + rate) ** years\n"
            "print(f'سود ساده در پایان سال پنجم: {simple:,.0f}')\n"
            "print(f'سود مرکب در پایان سال پنجم: {compound:,.0f}')\n"
            "print(f'اختلاف: {compound - simple:,.0f}')",
            "مقایسه‌ی سود ساده و مرکب با محاسبه‌ی واقعی",
        )
    safe = topic.replace('"', " ").replace("'", " ")
    return (
        "import statistics\n"
        'text = """' + safe + '"""\n'
        "words = text.split()\n"
        "print('تعداد کلمه:', len(words))\n"
        "print('میانگین طول کلمه:', round(statistics.mean(len(w) for w in words), 2) if words else 0)\n",
        "تحلیل آماری سریع خودِ درخواست (طول و تعداد کلمات)",
    )


_STOP_PHRASES = ("حالا ادامه بده", "(اگر کار تمام", "## ", "### ", "```")


def _clean_out(s: str, limit: int = 240) -> str:
    """خروجی ابزار را از متن‌های آمیخته با دستور/ساختار پاک می‌کند."""
    for stop in _STOP_PHRASES:
        if stop in s:
            s = s.split(stop, 1)[0]
    s = re.split(r"\n\s*\n", s)[0]
    return re.sub(r"\s+", " ", s).strip()[:limit]


def _tool_output(body: dict) -> str:
    """خروجی واقعی ابزار را از متن پاسخ خبره‌ها بیرون می‌کشد (برای گزارش داور)."""
    txt = _last_user(body)
    m = re.search(r"خروجی:\s*(.*?)(?:\n\n|\n```|$)", txt, re.S)
    if not m:
        m = re.search(r"\[نتیجه‌ی \w+\]\s*(.*?)(?:\n\n|$)", txt, re.S)
    return _clean_out(m.group(1), 220) if m else ""


def _original_request(body: dict) -> str:
    """اولین پیام کاربر که «درخواست» است (نه نتیجه‌ی ابزار)."""
    for m in body.get("messages") or []:
        if m.get("role") != "user":
            continue
        c = m.get("content") or ""
        if "[نتیجه‌ی" in c or c.startswith("نتیجه‌ی ابزارها"):
            continue
        for marker in ("## خواسته‌ی فعلی", "## خواسته کاربر",   # سرفصل‌های کارگزار
                       "## درخواست فعلی کاربر", "## درخواست کاربر",
                       "## پرسش فعلی", "## پرسش کاربر"):      # سرفصل‌های پنل خبرگان
            if marker in c:
                c = c.split(marker, 1)[-1]
        for cut in ("## معیار", "## پاسخ خبرگان", "## یافته", "### پاسخ", "## نقد"):
            if cut in c:
                c = c.split(cut, 1)[0]
        c = re.sub(r"(?m)^\s*#{1,6}.*$", " ", c)      # تیترهای مارک‌داونِ سرصفحه‌ها
        c = re.sub(r"\s+", " ", c).strip()
        if c:
            return c[:280]
    return _topic(body)


def _code_template(goal: str) -> tuple[str, str]:
    """برنامه‌های واقعیِ آماده از پوشه‌ی mega/templates (برای حالت بدون کلید)."""
    g = goal
    if any(k in g for k in ("تکراری", "duplicate")):
        name = "find_duplicates.py"
    elif any(k in g for k in ("مرتب", "سازمان", "organize", "پسوند")):
        name = "organize_files.py"
    else:
        name = "report_tool.py"
    path = Path(__file__).resolve().parent / "templates" / name
    try:
        return name, path.read_text(encoding="utf-8")
    except Exception:
        return name, "print('این فایل موقتاً در دسترس نیست.')\n"


def _runner_for(goal: str) -> str:
    """کد اجرای همان برنامه‌ی نوشته‌شده (اجرای واقعی + دیدن خروجی)."""
    fname, _ = _code_template(goal)
    return ("import subprocess, sys\n"
            f"r = subprocess.run([sys.executable, '{fname}'], capture_output=True, text=True, timeout=120)\n"
            "print('خروجی استاندارد:')\nprint(r.stdout[-3000:] or '(خالی)')\n"
            "print('خطا:')\nprint(r.stderr[-1500:] or '(بدون خطا)')\n"
            "print('کد خروج:', r.returncode)")


def wants_photo_ref(goal: str) -> bool:
    """آیا کاربر می‌خواهد از «عکس خودش» استفاده شود؟"""
    return any(k in goal for k in ("این عکس", "همین عکس", "این تصویر", "همین تصویر", "عکس خودم",
                                   "تصویر خودم", "این فایل", "همین فایل", "آپلود", "فرستادم",
                                   "پس‌زمینه")) or bool(__import__("re").search(r"[\w/\\-]+\.(png|jpe?g|webp)", goal, __import__("re").I))


# ------------------------------------------------------------------ پاسخ‌ها
def answer(role: str, body: dict, model: str) -> str:
    topic = _topic(body)
    if role == "agent":
        # مدل نمایشی چرخه‌ی واقعی کارگزار را اجرا می‌کند: ابزار واقعی → فایل واقعی → تحویل
        txt = "\n".join(m.get("content", "") for m in (body.get("messages") or []))
        done = txt.count("[نتیجه‌ی")
        goal = _original_request(body)
        gl = goal.lower()
        wants_video = any(k in goal for k in ("تبلیغ", "ویدیو", "فیلم", "کلیپ", "ریلز")) or "video" in gl
        wants_image = any(k in goal for k in ("پوستر", "تصویر", "بنر", "اسلاید")) or "poster" in gl
        wants_analyze = any(k in goal for k in ("تحلیل", "بررسی", "آنالیز", "بخوان", "چک کن",
                                                "اشکال", "خطا", "کیفیت")) or "analyz" in gl
        # فایل‌های آپلودی کاربر (مسیرها در پیام سیستم هستند) — بر اساس نوع خواسته انتخاب می‌شوند
        upaths = [u for u in re.findall(r"^-\s+`([^`]+)`\s+\(", txt, re.M) if Path(u).is_file()]

        def pick(kind_wanted: str) -> str:
            from .analyze import kind_of
            groups: dict[str, list[str]] = {}
            for u in upaths:
                try:
                    groups.setdefault(kind_of(Path(u)), []).append(u)
                except Exception:
                    continue
            if kind_wanted == "image":
                return (groups.get("image") or [""])[0]
            if kind_wanted == "data":
                return (groups.get("data") or groups.get("code") or groups.get("text")
                        or groups.get("doc") or [""])[0]
            for k in ("image", "data", "code", "text", "doc", "audio", "video", "archive"):
                if groups.get(k):
                    return groups[k][0]
            return upaths[0] if upaths else ""

        wants_ref = wants_photo_ref(goal)
        src = (pick("image") if (wants_image or wants_video or (wants_ref and not wants_analyze))
               else pick("data") if wants_analyze else pick("any"))
        img_src = pick("image")

        # ۱) تحلیل فایل آپلودی (هر نوعی)
        if done == 0 and wants_analyze and src:
            return ("برنامه: فایل را واقعاً باز می‌کنم، اندازه می‌گیرم، آمار/خطاها را درمی‌آورم و "
                    "اگر لازم باشد نمودار می‌کشم.\n\n```tool\n"
                    + json.dumps({"name": "analyze_file",
                                  "args": {"path": src, "question": goal[:200]}},
                                 ensure_ascii=False) + "\n```")
        # ۲) از عکس کاربر پوستر بساز
        if done == 0 and wants_image and img_src and wants_ref:
            return ("از همان عکس خودت استفاده می‌کنم: برش هوشمند به نسبت دلخواه + پرده‌ی تیره + "
                    "چیدمان متن فارسی.\n\n```tool\n"
                    + json.dumps({"name": "poster_from_photo",
                                  "args": {"photo": img_src, "path": "poster.png",
                                           "title": _brand_from_topic(goal) or "پوستر",
                                           "subtitle": "ساخته‌شده از عکس خودت",
                                           "lines": ["کیفیت حرفه‌ای", "تحویل فوری"],
                                           "badge": "امروز", "caption": "همین حالا شروع کن",
                                           "ratio": "9:16", "theme": "بنفش شب"}},
                                 ensure_ascii=False) + "\n```")
        # ۳) از عکس کاربر تبلیغ ویدیویی بساز
        if done == 0 and wants_video and img_src and wants_ref:
            return ("عکس خودت را پس‌زمینه‌ی ویدیو می‌کنم و صحنه‌ها را روی آن می‌چینم.\n\n```tool\n"
                    + json.dumps({"name": "make_ad",
                                  "args": {"topic": goal[:70] or "محصول تو", "path": "tabliq.mp4",
                                           "image": img_src, "ratio": "9:16",
                                           "voice": "fa-IR-FaridNeural", "brand": "", "music": True}},
                                 ensure_ascii=False) + "\n```")

        if done == 0 and wants_video:
            return ("برنامه: صحنه‌ها را می‌چینم، صداگذاری می‌کنم و با ffmpeg تدوین می‌کنم.\n\n```tool\n"
                    + json.dumps({"name": "make_ad",
                                  "args": {"topic": goal[:70] or "محصول تو", "path": "tabliq.mp4",
                                           "ratio": "9:16", "voice": "fa-IR-FaridNeural",
                                           "brand": "", "music": True}}, ensure_ascii=False)
                    + "\n```")
        if done == 0 and wants_image:
            return ("یک پوستر با چیدمان فارسی می‌سازم.\n\n```tool\n"
                    + json.dumps({"name": "make_image",
                                  "args": {"path": "poster.png",
                                           "title": _brand_from_topic(goal) or goal[:40],
                                           "subtitle": "ساخته‌شده توسط MEGA-AI",
                                           "lines": ["کیفیت حرفه‌ای", "تحویل سریع"],
                                           "theme": "طلایی لوکس",
                                           "ratio": "9:16", "badge": "امروز"}}, ensure_ascii=False)
                    + "\n```")
        wants_code = any(k in goal for k in ("پایتون", "برنامه", "کد", "اسکریپت", "تابع", "الگوریتم",
                                             "برنامه‌ای", "نرم‌افزار", "ماژول")) or "python" in gl
        if done == 0 and wants_code:
            fname, code = _code_template(goal)
            return (f"برنامه‌ی اجرا: کد واقعی را می‌نویسم، بعد اجرایش می‌کنم و خروجی را می‌بینم.\n\n"
                    "```tool\n" + json.dumps({"name": "write_file",
                                              "args": {"path": fname, "content": code}},
                                             ensure_ascii=False) + "\n```")
        if done == 1 and wants_code and not (wants_video or wants_image or wants_analyze):
            return ("حالا همان فایل را واقعاً اجرا می‌کنم و خروجی‌اش را می‌بینم.\n\n```tool\n"
                    + json.dumps({"name": "python", "args": {"code": _runner_for(goal)}},
                                 ensure_ascii=False) + "\n```")
        if done == 0:
            code = ("import math\n"
                    "print('محاسبه‌ی آزمایشی:', sum(i * i for i in range(1, 101)))\n"
                    "print('جذر ۲ تا ۶ رقم:', round(math.sqrt(2), 6))")
            return ("برنامه‌ی اجرا: اول یک بررسی محاسباتی واقعی، بعد ساخت یک فایل تحویلی، بعد گزارش.\n\n"
                    "```tool\n" + json.dumps({"name": "python", "args": {"code": code}},
                                             ensure_ascii=False) + "\n```")
        if done == 1 and not (wants_video or wants_image or wants_analyze):
            page = ("<!doctype html><html lang=fa dir=rtl><meta charset=utf-8>"
                    "<title>خروجی کارگزار</title>"
                    "<body style='font-family:Tahoma;background:#0b1020;color:#eaeefb;padding:40px'>"
                    "<h1>خروجی ساخته‌شده توسط MEGA-AI</h1>"
                    f"<p>خواسته: {goal[:120]}</p>"
                    "<p>این فایل به‌صورت واقعی در پوشه‌ی کاری ساخته شد.</p></body></html>")
            return ("محاسبه انجام شد. حالا خروجی قابل تحویل را می‌سازم.\n\n```tool\n"
                    + json.dumps({"name": "write_file",
                                  "args": {"path": "khorooji.html", "content": page}},
                                 ensure_ascii=False) + "\n```")
        # پایان: گزارش تحویل
        analyzed = wants_analyze and src
        coded = wants_code and not analyzed
        if coded:
            made = "برنامه‌ی پایتون (نوشته و اجرا شد)"
        made = ("تحلیل واقعی فایل" if analyzed else
                "ویدیوی تبلیغاتی" if wants_video else "پوستر" if wants_image else "پرونده‌ی خروجی")
        step2 = {
            "تحلیل واقعی فایل": ("۲. فایل را واقعاً باز کردم: اندازه‌ها/آمار/خطاها را درآوردم و نمودار کشیدم."),
            "ویدیوی تبلیغاتی": ("۲. صحنه‌ها را ساختم، صداگذاری کردم و با ffmpeg تدوین کردم"
                                + (" (عکس خودت پس‌زمینه شد)." if src else ".")),
            "پوستر": ("۲. پوستر را با فونت فارسی چیدم" + (" و عکس خودت را پس‌زمینه گذاشتم." if src else ".")),
            "پرونده‌ی خروجی": "۲. کد را واقعاً اجرا کردم و خروجی ساختم.",
            "برنامه‌ی پایتون (نوشته و اجرا شد)": "۲. فایل کد را نوشتم و همان‌جا اجرا کردم؛ خروجی واقعی در گزارش بالا آمده.",
        }[made]
        file_hint = ("فایل برنامه + خروجی اجرا" if coded else
                     "گزارش تحلیل + نمودارها" if analyzed else
                     "tabliq.mp4" if wants_video else "poster.png" if wants_image else "khorooji.html")
        return ("```tool\n" + json.dumps({
            "name": "finish", "args": {"answer": (
                "## انجام شد\n"
                f"**خواسته:** {goal[:160]}\n\n"
                "### چه کاری واقعاً اجرا شد\n"
                f"1. برنامه‌ریزی صحنه‌ها و متن برای: {goal[:80]}\n"
                f"{step2}\n"
                "3. فایل در پوشه‌ی همین نشست ذخیره شد و لینک دانلودش پایین آمده.\n\n"
                f"### فایل تحویلی\n- `{file_hint}`\n\n"
                "> ⚠️ این اجرا با «مدل نمایشی داخلی» انجام شد (هیچ کلید API ثبت نشده) — اما ویدیو/تصویر "
                "**واقعی** است، چون کارخانه‌ی محتوا به مدل وابسته نیست و روی همین سرور اجرا می‌شود. "
                "با ثبت کلید، متن و سناریو را هم مدل‌های واقعی (GPT / Claude / Gemini / Grok) می‌نویسند.")}},
            ensure_ascii=False) + "\n```")

    if role == "router":
        return json.dumps({
            "task_type": "code" if any(k in topic for k in ("کد", "برنامه", "اسکریپت", "python", "تابع"))
                         else "general",
            "difficulty": 3,
            "needs_web": any(k in topic for k in ("قیمت", "اخبار", "امروز", "آخرین", "آمار")),
            "needs_tools": True,
            "language": "fa" if re.search(r"[\u0600-\u06FF]", topic) else "en",
            "plan": ["تحلیل درخواست و شکستن به بخش‌ها",
                     "بررسی تجربی با اجرای کد",
                     "پاسخ مستقل هر خبره از زاویه‌ی خودش",
                     "نقد متقابل و یافتن خطاها",
                     "سنتز پاسخ نهایی و بازبینی"],
            "success_criteria": ["پاسخ به همه‌ی بخش‌های درخواست",
                                 "ادعاهای عددی با اجرای واقعی تأیید شده باشند",
                                 "خروجی قابل استفاده و اجرا باشد"],
            "expert_lenses": ["مهندس اجرا", "منتقد فنی", "تحلیلگر مسئله", "کارشناس کاربرد"],
        }, ensure_ascii=False)

    if role == "expert":
        user = _last_user(body)
        topic = _original_request(body)
        if "[نتیجه‌ی" not in user:
            code, _ = _recipe(topic)
            return ("برای اینکه حرفم ادعای بی‌مدرک نباشد، اول یک بررسی تجربی با ابزار پایتون انجام می‌دهم "
                    "و بعد پاسخ را بر پایه‌ی خروجی واقعی می‌نویسم.\n\n```tool\n"
                    + json.dumps({"name": "python", "args": {"code": code}}, ensure_ascii=False) + "\n```")
        m = re.search(r"\[نتیجه‌ی \w+\]\s*(.*?)(?:\n\n|$)", user, re.S)
        tool_out = _clean_out(m.group(1), 300) if m else ""
        return (f"## پاسخ خبره‌ی {model} (آزمایشی)\n"
                f"**موضوع:** {topic}\n\n"
                f"### ۱) آنچه تجربی بررسی شد\nتشخیص درخواست و اجرای یک محاسبه‌ی واقعی:\n\n"
                f"```\n{tool_out or 'خروجی ابزار دریافت شد'}\n```\n\n"
                "### ۲) پاسخ پیشنهادی\n"
                "۱. مسئله را به بخش‌های کوچک و مستقل بشکن تا هر بخش جداگانه آزمون‌پذیر باشد.\n"
                "۲. برای هر بخش یک معیار پذیرش عددی یا قابل‌سنجش تعیین کن.\n"
                "۳. بخش‌های محاسباتی/داده‌ای را حتماً با اجرای واقعی کد تأیید کن، نه با حدس.\n"
                "۴. نتیجه‌ی نهایی را با یک نمونه‌ی کوچک آزمون کن و بعد روی کل مسئله اعمال کن.\n\n"
                "### ۳) فرض‌ها و محدودیت‌ها\n"
                "- این پاسخ از **مدل نمایشی داخلی** است؛ برای پاسخ واقعی چند-مدلی، یک کلید API در بخش "
                "«کلیدهای API» ثبت کن (مثلاً OpenRouter با یک کلید به ده‌ها مدل دسترسی می‌دهد).\n"
                "- ساختار پاسخ‌ها، ابزارها، نقد و داوری در حالت واقعی دقیقاً همین است.")

    if role == "critic":
        return ("## نقد هر پاسخ\n"
                "### پاسخ A\n- خطا/ریسک: بدون خطای محاسباتی؛ تکیه بر خروجی واقعی ابزار.\n"
                "- نقطه‌ی قوی: گام‌های اجرایی و آزمون‌پذیر.\n- آنچه از قلم افتاده: سنجه‌ی موفقیت عددی.\n\n"
                "### پاسخ B\n- خطا/ریسک: کلی‌گویی در بخش اجرا.\n- نقطه‌ی قوی: ساختار روشن.\n"
                "- آنچه از قلم افتاده: نمونه‌ی واقعی.\n\n"
                "## تناقض‌ها\nاختلاف اصلی روی «عمق جزئیات» است؛ پاسخ دارای خروجی واقعی ابزار دقیق‌تر است.\n\n"
                "## امتیاز\n```json\n{\"scores\": {\"A\": 8.5, \"B\": 6.5}, \"verdict\": \"A دقیق‌تر و اجرایی‌تر\"}\n```")

    if role == "judge":
        names = _panel_names(body)
        tool_out = _tool_output(body)
        scores = {n: round(7.4 + (i % 3) * 0.5 + (0.2 if i == 0 else 0), 1) for i, n in enumerate(names)}
        return ("# پاسخ نهایی (ترکیب پنل خبرگان)\n\n"
                f"**درخواست:** {topic}\n\n"
                "## جمع‌بندی\n"
                "درخواست به چند گام اجرایی شکسته شد و بخش محاسباتی آن با اجرای واقعی کد بررسی شد"
                f"{(' — خروجی ابزار: `' + tool_out + '`') if tool_out else ''}. "
                "پاسخ‌ها از چند زاویه (اجرا، نقد، کاربرد) با هم مقایسه و تناقض‌هایشان حل شد.\n\n"
                "## گام‌های پیشنهادی\n"
                "1. مسئله را به بخش‌های مستقل بشکن و برای هرکدام معیار پذیرش بگذار.\n"
                "2. بخش‌های عددی/داده‌ای را با کد واقعی آزمون کن (خروجی، ملاک است نه حدس).\n"
                "3. با یک نمونه‌ی کوچک اعتبارسنجی کن، بعد کل مسئله را اجرا کن.\n"
                "4. نتیجه و محدودیت‌ها را شفاف مستند کن.\n\n"
                "## سهم مدل‌ها\n"
                + "\n".join(f"- **{n}**: " + ("اجرای ابزار و کد" if i == 0 else
                                             "ساختاردهی و پوشش جوانب" if i == 1 else "نقد و اصلاح جزئیات")
                           for i, n in enumerate(names)) +
                "\n\n> ⚠️ این خروجی از **مدل نمایشی داخلی** است (هیچ کلید API ثبت نشده). "
                "با ثبت کلید، همین خط تولید با مدل‌های واقعی GPT/Claude/Gemini/Grok/DeepSeek اجرا می‌شود.\n\n"
                "```json\n" + json.dumps({"scores": scores, "confidence": 0.62, "open_issues":
                                          ["پاسخ با مدل واقعی اعتبارسنجی نشده"]}, ensure_ascii=False) + "\n```")

    if role == "verifier":
        return json.dumps({"ok": True, "issues": ["خروجی آزمایشی است، نه پاسخ مدل واقعی"],
                           "must_fix": [], "confidence": 0.6}, ensure_ascii=False)

    return "پاسخ آزمایشی مدل نمایشی."


# ------------------------------------------------------------------ اندپوینت‌ها
def sse(text: str):
    def chunks():
        yield f'data: {json.dumps({"choices": [{"delta": {"role": "assistant"}}]})}\n\n'
        for i in range(0, len(text), 28):
            yield f'data: {json.dumps({"choices": [{"delta": {"content": text[i:i + 28]}}]}, ensure_ascii=False)}\n\n'
            time.sleep(0.01)
        yield ('data: ' + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}],
                                      "usage": {"total_tokens": 420}}) + "\n\n")
        yield "data: [DONE]\n\n"
    return StreamingResponse(chunks(), media_type="text/event-stream")


def _guard(request: Request) -> Optional[JSONResponse]:
    if BRIDGE["active"] and not _is_local(str(request.client.host if request.client else "")):
        return JSONResponse({"error": "demo endpoint"}, status_code=403)
    return None


def _is_local(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost", "testclient")


@app.get("/v1/models")
async def models(request: Request):
    g = _guard(request)
    if g:
        return g
    return {"data": [{"id": m, "object": "model"} for m in DEMO_MODELS]}


@app.post("/v1/chat/completions")
async def completions(request: Request, body: dict):
    g = _guard(request)
    if g:
        return g
    system = next((m.get("content", "") for m in body.get("messages", []) if m.get("role") == "system"), "")
    model = body.get("model") or "demo-gpt"
    text = answer(role_of(system), body, model)
    if body.get("stream"):
        return sse(text)
    return {"choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"total_tokens": 420}}


# ------------------------------------------------------------------ پل نمایشی
def enable(host_app, port: int) -> None:
    """مدل نمایشی را به‌عنوان پرووایدر «آزمایشی» به سیستم وصل می‌کند."""
    from .config import PROVIDERS
    if BRIDGE["active"]:
        return
    host_app.mount("/mock", app)
    p = PROVIDERS["openai"]
    if not getattr(p, "base_url_original", None):
        p.base_url_original = p.base_url          # آدرس واقعی را برای تست حفظ کن
    p.key_override = "demo-mode"
    p.base_url = f"http://127.0.0.1:{port}/mock/v1"
    BRIDGE["active"] = True


def disable() -> None:
    """بعد از ورود کلید واقعی، مدل نمایشی را کنار می‌گذارد."""
    from .config import PROVIDERS
    if not BRIDGE["active"]:
        return
    p = PROVIDERS["openai"]
    p.key_override = None
    p.base_url = (os.environ.get("OPENAI_BASE_URL")
                  or getattr(p, "base_url_original", None)
                  or "https://api.openai.com/v1")
    BRIDGE["active"] = False


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MOCK_PORT", "8123"))
    print(f"مدل نمایشی روی http://127.0.0.1:{port}/v1  (مدل‌ها: {', '.join(DEMO_MODELS)})")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
