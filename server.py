"""
MehranAiShabestar  |  سرور وب (FastAPI)
------------------------------------------------
  python server.py            → http://localhost:8000
رابط وب فارسی، اجرای زنده (SSE) و مدیریت کلیدها.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from mega.agent import MegaAgent
from mega.config import (APP_VERSION, ENV_PATH, ROOT, SETTINGS, WEB_DIR, WORKSPACE, configured_providers, key_status,
                         has_real_keys, real_configured_providers,
                         load_env, save_keys, PROVIDERS)
from mega.media import THEMES, VOICES, make_ad, make_image, make_video, stt, tts
from mega.memory import MEMORY
from mega.orchestrator import Orchestrator
from mega.providers import clear_cache, health_check_all, list_models, test_provider
from mega.skills import SkillBox, installed_skills, update_libraries
from mega.telegram_bot import TelegramBot

app = FastAPI(title="MehranAiShabestar", docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

load_env()
STATE: dict = {"settings": SETTINGS}


# ── رمز اختیاری (برای وقتی برنامه روی سرور عمومی اجرا می‌شود) ──────────────
# در ویندوز:  set MEGA_PASSWORD=mehran   ← قبل از اجرا
# یا در فایل .env بگذار:  MEGA_PASSWORD=mehran
# نکته: رمز «mehran» همیشه قبول است، حتی اگر .env رمز دیگری داشته باشد.
# اگر MEGA_PASSWORD خالی باشد، برنامه بدون رمز کار می‌کند.
ALWAYS_OK_PASSWORD = "mehran"


AUTH_COOKIE = "mega_auth"


def _auth_token(pw: str) -> str:
    import hashlib
    return hashlib.sha256(("mega-ai|" + pw).encode("utf-8")).hexdigest()


@app.middleware("http")
async def _password_gate(request: Request, call_next):
    pw = os.environ.get("MEGA_PASSWORD", "").strip()
    if not pw:
        return await call_next(request)

    accepted = [pw, ALWAYS_OK_PASSWORD]

    # کوکی = ورود قبلی (تا درخواست‌های داخلی پنل هم بدون پرسیدن رمز رد شوند)
    from_cookie = request.cookies.get(AUTH_COOKIE) == _auth_token(pw)

    import base64
    import hmac
    ok = from_cookie
    head = request.headers.get("authorization", "")
    if not ok and head[:6].lower() == "basic ":
        try:
            raw = base64.b64decode(head[6:]).decode("utf-8", "ignore")
            _, _, given = raw.partition(":")
            given = given.strip()
            ok = any(hmac.compare_digest(given, p) for p in accepted)
        except Exception:  # noqa: BLE001
            ok = False
    if ok:
        resp = await call_next(request)
        if not from_cookie:                      # ورود تازه → کوکی بگذار
            resp.set_cookie(AUTH_COOKIE, _auth_token(pw), max_age=60 * 60 * 24 * 30,
                            httponly=True, samesite="lax", path="/")
        return resp
    return JSONResponse(
        {"ok": False, "error": "این سرور رمز دارد. نام کاربری مهم نیست؛ فقط رمز را بزن."},
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="MehranAiShabestar"'},
    )


def _listen_port() -> int:
    """پورت شنود: اول PORT (میزبان‌های ابری مثل Render)، بعد MEGA_PORT، بعد ۸۰۰۰."""
    for key in ("PORT", "MEGA_PORT"):
        raw = os.environ.get(key)
        if raw:
            try:
                return int(raw)
            except ValueError:
                pass
    return 8000


def _maybe_bridge() -> None:
    """هوش را وصل کن: اول هوشِ خودِ سرور (Ollama/…)، وگرنه مدل نمایشی.

    اگر روی همین کامپیوتر Ollama (یا LM Studio / llama.cpp) نصب و روشن باشد،
    مدل واقعاً روی سرور خودت اجرا می‌شود: بدون کلید، بدون اینترنت، بدون تحریم.
    """
    try:
        from mega import local_llm
        found = local_llm.detect()
        if found:
            local_llm.activate(found)
            print(f"[OK] Local AI found: {found['kind']} -> {found['base_url']} "
                  f"({len(found['models'])} model(s))", flush=True)
            return
    except Exception as e:  # noqa: BLE001
        print(f"[i] Local AI check skipped: {type(e).__name__}", flush=True)

    from mega import demo_model
    if not configured_providers():
        demo_model.enable(app, _listen_port())


@app.get("/")
async def index():
    """پنل کاربری آسان (پیش‌فرض)."""
    simple = WEB_DIR / "simple.html"
    return FileResponse(simple if simple.exists() else WEB_DIR / "index.html")


@app.get("/guide")
async def guide():
    """راهنمای ۲ دقیقه‌ای گرفتن کلید (فارسی، با لینک مستقیم)."""
    return FileResponse(WEB_DIR / "guide.html")


@app.get("/terminal")
async def terminal():
    """ترمینال: خواسته را فارسی مینویسی، کارگزار واقعاً انجام میدهد."""
    return FileResponse(WEB_DIR / "terminal.html")


@app.get("/advanced")
async def advanced():
    """رابط کامل حرفه‌ای."""
    return FileResponse(WEB_DIR / "index.html")


@app.get("/tv")
async def tv_page():
    """📺 تلویزیون: کانال‌های آزاد فارسی/آذربایجانی/ترکی (رایگان، بدون اشتراک)."""
    return FileResponse(WEB_DIR / "tv.html")


@app.get("/api/tv")
async def tv_api(refresh: int = 0):
    """فهرست کانال‌ها (کش ۱۲ ساعته؛ با refresh=1 از نو گرفته می‌شود)."""
    from mega import tv as tvmod
    data = await asyncio.to_thread(tvmod.load, bool(refresh))
    items = data.get("items") or []
    return {"ok": True, "count": len(items), "updated": data.get("updated"), "items": items}


@app.get("/more")
async def more_page():
    """✨ افزودنی‌ها: آب‌وهوا، رادیو، اخبار، مترجم (همه رایگان و بدون کلید)."""
    return FileResponse(WEB_DIR / "more.html")


@app.get("/api/addons")
async def addons_status():
    """فهرست افزودنی‌های نصب‌شده برای داشبورد."""
    from mega import addons
    return addons.status()


@app.get("/api/weather")
async def weather_api(city: str = "\u062a\u0628\u0631\u06cc\u0632"):
    """آب‌وهوای امروز + ۵ روز آیندهٔ یک شهر (فارسی)."""
    from mega import addons
    return await asyncio.to_thread(addons.weather, city)


@app.get("/api/radio")
async def radio_api(country: str = "", q: str = "", refresh: int = 0):
    """ایستگاه‌های رادیوی اینترنتی رایگان."""
    from mega import addons
    return await asyncio.to_thread(addons.radio, country, q, bool(refresh))


@app.get("/api/news")
async def news_api(refresh: int = 0):
    """تیترهای تازه از خبرگزاری‌های فارسی (RSS)."""
    from mega import addons
    return await asyncio.to_thread(addons.news, bool(refresh))


@app.post("/api/translate")
async def translate_api(payload: dict):
    """ترجمهٔ متن — بدون کلید (MyMemory)."""
    from mega import addons
    return await asyncio.to_thread(addons.translate, str(payload.get("text") or ""),
                                   str(payload.get("to") or "en"),
                                   str(payload.get("from") or "fa"))


@app.get("/assets/{name}")
async def asset_file(name: str):
    """فایل‌های برند (لوگو، فونت) — از پوشه‌ی assets سرو می‌شوند."""
    from pathlib import Path as _P
    safe = _P(name).name                       # جلوگیری از پیمایش مسیر
    target = _P(__file__).resolve().parent / "assets" / safe
    if not target.is_file():
        return JSONResponse({"ok": False, "error": "فایل پیدا نشد"}, status_code=404)
    return FileResponse(target)




# اندازهٔ تقریبی مدل‌های شناخته‌شده (میلیارد پارامتر) — برای نشان «مغز فعال»
BRAIN_SIZE = {
    "kimi-k2": (1000, "۱ تریلیون"), "deepseek-r1": (671, "۶۷۱ میلیارد"),
    "qwen3-235b": (235, "۲۳۵ میلیارد"), "llama-4-maverick": (400, "۴۰۰ میلیارد"),
    "llama-4-scout": (109, "۱۰۹ میلیارد"), "gpt-oss-120b": (120, "۱۲۰ میلیارد"),
    "nemotron-3-120b": (120, "۱۲۰ میلیارد"), "nemotron": (120, "۱۲۰ میلیارد"),
    "llama-3.3-70b": (70, "۷۰ میلیارد"), "qwen2.5-coder-32b": (32, "۳۲ میلیارد"),
    "qwen3-32b": (32, "۳۲ میلیارد"), "gemma-4-26b": (26, "۲۶ میلیارد"),
    "gemma-3-27b": (27, "۲۷ میلیارد"), "llama-3.1-8b": (8, "۸ میلیارد"),
    "mistral-small": (24, "۲۴ میلیارد"), "deepseek-chat": (671, "۶۷۱ میلیارد"),
    "qwen3.8-27b": (27, "۲۷ میلیارد"),
    "openai-fast": (20, "۲۰ میلیارد (بی‌کلید)"),
    "nemotron-3-ultra-550b": (550, "۵۵۰ میلیارد"), "nemotron-3-super-120b": (120, "۱۲۰ میلیارد"),
    "inking": (0, ""), "inkling": (0, ""),
}


def _brain_label() -> dict:
    """بزرگ‌ترین مغزی که الان فعال است + اندازه‌اش (۱۲۰ میلیارد / ۴۰۰ میلیارد / ۱ تریلیون)."""
    try:
        active = [p.id for p in real_configured_providers()]
    except Exception:  # noqa: BLE001
        active = []
    best = {"provider": "", "model": "", "params": 0, "label": "—", "display": "🧠 مغز فعال نیست"}
    for pid in active:
        p = PROVIDERS.get(pid)
        for m in (getattr(p, "default_models", None) or [])[:5]:
            low = m.lower()
            size, label = 0, ""
            # بلندترین تطابق برنده است (وگرنه «nemotron» عمومی‌تر از «nemotron-3-ultra-550b» می‌برد)
            hits = [(len(k), v) for k, v in BRAIN_SIZE.items() if k in low]
            if hits:
                size, label = max(hits, key=lambda x: x[0])[1]
            if not size:                      # ناشناخته → از نام حدس بزن (حالت MoE مثل a22b را رد کن)
                guess = re.sub(r"[-_]a\d+b", "", low).replace("-", "").replace("_", "")
                n = re.search(r"(\d+\.?\d*)\s*([bt])(?![a-z0-9])", guess)
                if n:
                    size = float(n.group(1)) * (1000 if n.group(2) == "t" else 1)
                    label = f"{int(size)} میلیارد"
            if size > best["params"]:
                best = {"provider": pid, "model": m, "params": size, "label": label,
                        "display": f"🧠 {label} — {m.split('/')[-1]}"}
    return best


@app.get("/api/health")
async def health():
    from mega import demo_model
    s = STATE["settings"]
    return {
        "ok": True,
        "version": APP_VERSION,
        "brain": _brain_label(),
        "demo": not has_real_keys(),
        "demo_model": demo_model.BRIDGE["active"],
        "providers": key_status(),
        "active": [p.id for p in real_configured_providers()],
        "settings": {k: getattr(s, k) for k in s.__dataclass_fields__},
        "stats": MEMORY.stats(),
    }


async def _verify_provider(pid: str) -> dict:
    """کلید را واقعاً تست می‌کند تا کاربر بداند کار می‌کند یا نه."""
    p = PROVIDERS.get(pid)
    if not p or not p.configured:
        return {"ok": False, "detail": "کلید خالی است"}
    if pid == "cloudflare" and not (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip():
        return {"ok": False, "detail": "شناسهٔ حساب (Account ID) پیدا نشد — آن را هم بفرست"}
    try:
        import httpx
        if pid == "cloudflare":          # تست واقعی با یک پیام کوتاه
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.post(p.api_base.rstrip("/") + "/chat/completions",
                                 headers={"Authorization": f"Bearer {p.key}"},
                                 json={"model": (p.default_models or ["@cf/meta/llama-3.1-8b-instruct-fp8-fast"])[0],
                                       "messages": [{"role": "user", "content": "سلام"}],
                                       "max_tokens": 5})
            if r.status_code == 200:
                return {"ok": True, "detail": "توکن سالم است و پاسخ داد"}
            if r.status_code in (401, 403):
                return {"ok": False, "detail": "توکن پذیرفته نشد — دوباره کپی کن"}
            return {"ok": False, "detail": f"پاسخ سرور: {r.status_code}"}
        url = p.api_base.rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {p.key}"}
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(url, headers=headers)
        if r.status_code == 200:
            n = len((r.json() or {}).get("data") or [])
            return {"ok": True, "detail": f"کلید سالم است ({n} مدل در دسترس)"}
        if r.status_code in (401, 403):
            return {"ok": False, "detail": "کلید پذیرفته نشد — دوباره کپی کن"}
        return {"ok": False, "detail": f"پاسخ سرور: {r.status_code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"ارتباط برقرار نشد: {type(e).__name__}"}


def _detect_key(value: str) -> str:
    """از شکلِ کلید می‌فهمد مربوط به کدام سرویس است (کاربر لازم نیست چیزی انتخاب کند)."""
    v = value.strip()
    low = v.lower()
    if low.startswith("aa-"):
        return "AVALAI_API_KEY"
    if low.startswith("gsk_"):
        return "GROQ_API_KEY"
    if low.startswith("sk-or-") or low.startswith("sk-or-v1"):
        return "OPENROUTER_API_KEY"
    if low.startswith("sk-"):
        return "GAPGPT_API_KEY"
    if len(v) == 32 and all(c in "0123456789abcdefABCDEFabcdef" for c in v):
        return "CLOUDFLARE_ACCOUNT_ID"
    if len(v) >= 35 and all(c.isalnum() or c in "_-" for c in v):
        return "CLOUDFLARE_API_TOKEN"     # توکن ۴۰ کاراکتری Cloudflare
    return "GAPGPT_API_KEY"


async def _discover_cf_account(token: str) -> tuple[str, str]:
    """شناسهٔ حساب Cloudflare را بدون دخالت کاربر از خود سرویس می‌گیرد."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get("https://api.cloudflare.com/client/v4/accounts",
                            headers={"Authorization": f"Bearer {token}"})
        data = r.json() or {}
        res = data.get("result") or []
        if r.status_code == 200 and res:
            return str(res[0].get("id") or ""), str(res[0].get("name") or "")
    except Exception:  # noqa: BLE001
        pass
    return "", ""


@app.post("/api/keys")
async def set_keys(payload: dict):
    from mega import demo_model
    pairs: dict[str, str] = {}
    raw = str(payload.get("key") or "").strip()
    if raw:                                   # یک مقدار ساده: خودش تشخیص می‌دهد
        for part in raw.replace(",", " ").split():
            if re.fullmatch(r"[0-9a-fA-F]{32}", part):
                pairs["CLOUDFLARE_ACCOUNT_ID"] = part.lower()
                continue
            _u = re.search(r"/([0-9a-fA-F]{32})(?:/|$|\?)", part)
            if _u and ("." in part or "/" in part):   # آدرس داشبورد را چسبانده → شناسهٔ حساب
                pairs["CLOUDFLARE_ACCOUNT_ID"] = _u.group(1).lower()
                continue
            pairs[_detect_key(part)] = part
    for k, v in payload.items():              # حالت قدیمی: {"AVALAI_API_KEY": "..."}
        if isinstance(k, str) and k.lower() != "key" and str(v).strip():
            pairs[k.upper()] = str(v).strip()
    save_keys(pairs)

    note = ""
    if pairs.get("CLOUDFLARE_API_TOKEN") and not (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip():
        _acc_id, _acc_name = await _discover_cf_account(pairs["CLOUDFLARE_API_TOKEN"])
        if _acc_id:
            save_keys({"CLOUDFLARE_ACCOUNT_ID": _acc_id})
            note = f" — شناسهٔ حساب خودکار پیدا شد ({_acc_name or _acc_id[:8]})"
    if configured_providers():
        demo_model.disable()          # کلید واقعی آمد → مدل نمایشی کنار می‌رود
    verified = {}
    for pid in [p.id for p in configured_providers() if p.real_key]:
        verified[pid] = await _verify_provider(pid)
    good = [pid for pid, v in verified.items() if v.get("ok")]
    if good:
        msg = "✅ کلید کار می‌کند: " + ", ".join(good)
    elif verified:
        msg = "❌ کلید ذخیره شد ولی تست نشد: " + "؛ ".join(
            f"{k}: {v.get('detail','')}" for k, v in verified.items())
    else:
        msg = "کلید ذخیره شد." + note
    if good:
        msg += note
    return {"ok": True, "active": [p.id for p in configured_providers()],
            "providers": key_status(), "demo_model": demo_model.BRIDGE["active"],
            "verified": verified, "message": msg}


@app.get("/api/models")
async def models():
    """لیست مدل‌های واقعی هر پرووایدری که کلید دارد."""
    out = {}
    for pid, p in PROVIDERS.items():
        if p.configured:
            out[pid] = {"label": p.label, "models": (await list_models(pid))[:200]}
    return {"ok": True, "providers": out}


@app.post("/api/settings")
async def set_settings(payload: dict):
    s = STATE["settings"]
    for k, v in payload.items():
        if hasattr(s, k):
            try:
                cur = getattr(s, k)
                if isinstance(cur, bool):
                    v = bool(v)
                elif isinstance(cur, int) and not isinstance(cur, bool):
                    v = int(v)
                elif isinstance(cur, float):
                    v = float(v)
                setattr(s, k, v)
            except Exception:
                pass
    return {"ok": True, "settings": {k: getattr(s, k) for k in s.__dataclass_fields__}}


# ════════════════════════════════════════ 🧪 تست کامل سیستم
def _probe_hosts() -> list[tuple[str, str]]:
    """سایت‌هایی که باید از سرور کاربر باز شوند: (آدرس، برچسب)."""
    return [
        # ── سرویس‌های ایرانی (باید بدون فیلترشکن باز شوند)
        ("https://api.avalai.ir/v1/models", "AvalAI (ایرانی)"),
        ("https://api.gapgpt.app/v1/models", "GapGPT (ایرانی)"),
        ("https://api.metisai.ir/openai/v1/models", "MetisAI (ایرانی)"),
        ("https://api.winkapi.net/v1/models", "WinkAPI (ایرانی)"),
        ("https://sinoxapi.com/v1/models", "SinoxAPI (قوی‌ترین مدل‌های رایگان ایرانی)"),
        # ── جهانی (از ایران فیلترند → پروکسی لازم است)
        ("https://api.groq.com/openai/v1/models", "Groq (جهانی — سریع)"),
        ("https://openrouter.ai/api/v1/models", "OpenRouter (جهانی — ۵۵۰ میلیارد رایگان)"),
        ("https://api.cloudflare.com/client/v4/", "Cloudflare (وصل تو)"),
        ("https://api.openai.com/v1/models", "OpenAI"),
        ("https://generativelanguage.googleapis.com/v1beta/models", "Google Gemini"),
        ("https://api.telegram.org", "تلگرام"),
        # ── ابزارهای رایگان برنامه
        ("https://text.pollinations.ai/models", "Pollinations (هوش بی‌کلید)"),
        ("https://api.open-meteo.com/v1/forecast?latitude=35&longitude=51", "هواشناسی (بی‌کلید)"),
        ("https://de1.api.radio-browser.info/json/stations/topvote/2", "رادیو اینترنتی"),
        ("https://iptv-org.github.io/api/streams.json", "فهرست تلویزیون"),
        ("https://api.mymemory.translated.net/get?q=hi&langpair=en|fa", "مترجم (بی‌کلید)"),
        ("https://github.com", "GitHub (برای آپدیت)"),
        ("https://cdn.jsdelivr.net", "jsDelivr (برای آپدیت)"),
    ]


async def _selftest_host(client, url: str, label: str, proxy_note: str = "") -> dict:
    import time as _t
    t0 = _t.time()
    try:
        r = await client.get(url, timeout=8)
        ms = int((_t.time() - t0) * 1000)
        return {"name": label, "ok": True, "code": r.status_code, "ms": ms,
                "detail": f"باز است ({r.status_code}) در {ms} میلی‌ثانیه"}
    except Exception as e:  # noqa: BLE001
        ms = int((_t.time() - t0) * 1000)
        kind = type(e).__name__
        if "Timeout" in kind or "Connect" in kind or "Proxy" in kind:
            return {"name": label, "ok": False, "ms": ms,
                    "detail": "بسته است (پاسخ نداد)", "hint": proxy_note or "این سایت از شبکهٔ سرورت باز نمی‌شود"}
        return {"name": label, "ok": False, "ms": ms, "detail": f"{kind}", "hint": proxy_note or ""}


@app.get("/api/selftest")
async def selftest(deep: int = 0):
    """تست کامل همه بخش‌ها روی همین سرور (برای کاربر ایرانی که دسترسی از بیرون ندارد)."""
    import platform, shutil, time as _t
    import httpx
    from mega import skills as _skills

    st = STATE["settings"]
    out: dict = {"ok": True, "version": APP_VERSION, "sections": []}

    # ── ۱) سرور
    sys_items = [
        {"name": "نسخهٔ پایتون", "ok": True, "detail": platform.python_version()},
        {"name": "سیستم‌عامل", "ok": True, "detail": f"{platform.system()} {platform.release()}"},
    ]
    try:
        du = shutil.disk_usage(str(ROOT))
        free_gb = du.free / 1e9
        sys_items.append({"name": "فضای دیسک", "ok": free_gb > 1,
                          "detail": f"{free_gb:.1f} گیگابایت آزاد",
                          "hint": "" if free_gb > 1 else "دیسک پر است — فایل‌های workspace را پاک کن"})
    except Exception:  # noqa: BLE001
        pass
    ff = shutil.which("ffmpeg")
    sys_items.append({"name": "ffmpeg (ساخت ویدیو/صدا)", "ok": bool(ff),
                      "detail": "نصب است" if ff else "نصب نیست",
                      "hint": "" if ff else "برای استودیو/صدا: winget install ffmpeg یا از ffmpeg.org دانلود کن"})
    nd = shutil.which("node")
    sys_items.append({"name": "Node.js", "ok": bool(nd), "detail": "نصب است" if nd else "نصب نیست",
                      "hint": "" if nd else "برای بعضی ابزارها لازم است (اختیاری)"})
    try:
        probe = WORKSPACE / "_selftest.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        sys_items.append({"name": "نوشتن در پوشهٔ کار", "ok": True, "detail": "اجازه دارد"})
    except Exception as e:  # noqa: BLE001
        sys_items.append({"name": "نوشتن در پوشهٔ کار", "ok": False, "detail": str(e)[:80]})
    try:
        stats = MEMORY.stats()
        hist = MEMORY.prompts("", 1000)
        sys_items.append({"name": "پایگاه تاریخچه", "ok": stats.get("runs", 0) >= 0,
                          "detail": f"{stats.get('runs', 0)} اجرا · {len(hist)} پرامپت ذخیره‌شده · "
                                    f"امتیاز {stats.get('models', 0)} مدل"})
    except Exception as e:  # noqa: BLE001
        sys_items.append({"name": "پایگاه تاریخچه", "ok": False, "detail": str(e)[:80]})
    sys_items.append({"name": "رمز ورود", "ok": bool(os.environ.get("MEGA_PASSWORD") or ALWAYS_OK_PASSWORD),
                      "detail": "فعال است" if os.environ.get("MEGA_PASSWORD") else "فقط رمز پیش‌فرض"})
    out["sections"].append({"title": "🖥 سرور و سیستم", "items": sys_items})

    # ── ۲) ابزارهای داخلی
    tool_items = []
    try:
        names = sorted(n for n in dir(_skills.SkillBox) if n.startswith("_t_"))
        tool_items.append({"name": "جعبه‌ابزار کارگزار", "ok": len(names) >= 10,
                           "detail": f"{len(names)} ابزار فعال (کد، فایل، وب، ویدیو، صدا…)"})
    except Exception as e:  # noqa: BLE001
        tool_items.append({"name": "جعبه‌ابزار کارگزار", "ok": False, "detail": str(e)[:80]})
    for label, path in (("رابط اصلی (تب‌ها)", WEB_DIR / "index.html"),
                        ("رابط ساده", WEB_DIR / "simple.html"),
                        ("ترمینال", WEB_DIR / "terminal.html"),
                        ("تلویزیون", WEB_DIR / "tv.html"),
                        ("افزودنی‌ها", WEB_DIR / "more.html"),
                        ("راهنمای کلید", WEB_DIR / "guide.html")):
        tool_items.append({"name": label, "ok": path.exists(),
                           "detail": "هست" if path.exists() else "فایل نیست"})
    try:
        arts = list(WORKSPACE.rglob("*"))
        tool_items.append({"name": "پوشهٔ فایل‌های ساخته‌شده", "ok": True,
                           "detail": f"{len([a for a in arts if a.is_file()])} فایل"})
    except Exception:  # noqa: BLE001
        pass
    out["sections"].append({"title": "🧩 بخش‌های برنامه", "items": tool_items})

    # ── ۳) سرویس‌های هوش (هر کدام کلید دارد واقعاً تست می‌شود)
    prov_items = []
    configured = []
    for pid, p in PROVIDERS.items():
        if pid == "custom":
            continue
        if not p.key:
            prov_items.append({"name": f"{p.label} — {pid}", "ok": None,
                               "detail": "کلید نداری (خالی)"})
            continue
        configured.append((pid, p))
    if configured:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            async def one(pid: str, p) -> dict:
                base = p.api_base
                try:
                    if not getattr(p, "needs_key", True):        # سرویس عمومی: با یک گفتگوی کوتاه تست کن
                        rr = await client.post(f"{base.rstrip('/')}/chat/completions",
                                               headers={"content-type": "application/json"},
                                               json={"model": (p.default_models or ["openai"])[0],
                                                     "messages": [{"role": "user", "content": "سلام"}]},
                                               timeout=25)
                        if rr.status_code == 200:
                            return {"name": f"{p.label} — {pid}", "ok": True,
                                    "detail": "✅ بدون کلید کار می‌کند (سرویس عمومی)"}
                        return {"name": f"{p.label} — {pid}", "ok": False,
                                "detail": f"❌ پاسخ {rr.status_code}",
                                "hint": "این سرویس عمومی از شبکهٔ سرورت باز نیست"}

                    if p.kind == "gemini":
                        r = await client.get(f"{base}/models", params={"key": p.key}, timeout=12)
                    else:
                        r = await client.get(f"{base.rstrip('/')}/models",
                                             headers={"Authorization": f"Bearer {p.key}"}, timeout=12)
                    if r.status_code == 200:
                        data = r.json()
                        n = len(data.get("data") or data.get("models") or [])
                        return {"name": f"{p.label} — {pid}", "ok": True,
                                "detail": f"✅ کلید سالم · {n} مدل در دسترس"}
                    if r.status_code in (401, 403):
                        return {"name": f"{p.label} — {pid}", "ok": False,
                                "detail": f"❌ کلید رد شد ({r.status_code})",
                                "hint": "کلید را دوباره از پنل بگیر و در تب 🔑 کلیدها بچسبان"}
                    return {"name": f"{p.label} — {pid}", "ok": r.status_code < 500,
                            "detail": f"پاسخ {r.status_code}"}
                except Exception as e:  # noqa: BLE001
                    kind = type(e).__name__
                    blocked = "Timeout" in kind or "Connect" in kind or "Proxy" in kind
                    return {"name": f"{p.label} — {pid}", "ok": False,
                            "detail": "❌ دسترس نیست (شبکه)", "hint":
                            "سایتش از سرورت بسته است — پروکسی بگذار (تب 🔑 کلیدها)" if blocked else kind}
            prov_items.extend(await asyncio.gather(*[one(pid, p) for pid, p in configured]))
    out["sections"].append({"title": "🔌 سرویس‌های هوش (کلیددار)", "items": prov_items})

    # ── ۴) شبکه: از سرور تو چه چیزی باز می‌شود (ایرانی و جهانی) + پروکسی
    host_items = []
    proxy = (getattr(st, "proxy", "") or "").strip()
    note_ir = "سرویس ایرانی است؛ اگر بسته است یعنی شبکهٔ سرورت مشکل دارد (یا خود سرویس خوابیده)"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        probes = _probe_hosts()

        async def probe(url: str, label: str) -> dict:
            iranian = any(k in url for k in ("avalai", "gapgpt", "metisai", "winkapi", "sinoxapi"))
            return await _selftest_host(client, url, ("🇮🇷 " if iranian else "🌍 ") + label,
                                        proxy_note=note_ir if iranian else
                                        "از ایران بسته است — VPN/پروکسی لازم است (تب 🔑 کلیدها)")

        r1 = await asyncio.gather(*[probe(u, l) for u, l in probes])
        host_items.extend(r1)
        if proxy:
            try:
                async with httpx.AsyncClient(proxy=proxy, timeout=10, follow_redirects=True) as pc:
                    r = await pc.get("https://api.groq.com/openai/v1/models")
                    host_items.append({"name": "🔀 پروکسی تو", "ok": r.status_code < 500,
                                       "detail": f"کار می‌کند (پاسخ {r.status_code}) — سرویس‌های جهانی از این مسیر باز می‌شوند"})
            except Exception as e:  # noqa: BLE001
                host_items.append({"name": "🔀 پروکسی تو", "ok": False,
                                   "detail": f"کار نکرد: {type(e).__name__}",
                                   "hint": "آدرس پروکسی/پورت را چک کن — مثلاً http://127.0.0.1:10809"})
        else:
            host_items.append({"name": "🔀 پروکسی", "ok": None,
                               "detail": "تنظیم نشده (اگر سایت جهانی بسته است، بگذار)",
                               "hint": "تب 🔑 کلیدها → کادر پروکسی"})
    out["sections"].append({"title": "🌐 دسترسی شبکه از سرور تو", "items": host_items})

    # ── ۵) جمع‌بندی
    ok = sum(1 for sec in out["sections"] for it in sec["items"] if it.get("ok") is True)
    bad = sum(1 for sec in out["sections"] for it in sec["items"] if it.get("ok") is False)
    skip = sum(1 for sec in out["sections"] for it in sec["items"] if it.get("ok") is None)
    out["summary"] = {"ok": ok, "fail": bad, "skip": skip}
    out["verdict"] = ("همه‌چیز سالم است ✅" if bad == 0 else
                      f"{bad} مورد مشکل دارد ❌ — پایین‌تر راهنمای هر کدام نوشته شده")
    out["checked_at"] = _t.strftime("%Y-%m-%d %H:%M:%S")
    return out


@app.get("/api/history")
async def history(session: str = "", limit: int = 200):
    """تاریخچه: پرامپت‌ها (همه یا یک نشست) + فهرست نشست‌ها + امتیازها."""
    return {"ok": True, "sessions": MEMORY.session_list(60), "items": MEMORY.prompts(session, limit),
            "leaderboard": MEMORY.leaderboard(), "stats": MEMORY.stats()}


@app.post("/api/history")
async def history_change(payload: dict):
    """پاک کردن: یک پرامپت (delete_run) · یک نشست (delete_session) · همه‌چیز (clear)."""
    action = str(payload.get("action") or "clear")
    if action == "delete_run":
        n = MEMORY.delete_run(int(payload.get("id") or 0))
        return {"ok": True, "deleted": n, "message": f"{n} مورد پاک شد"}
    if action == "delete_session":
        n = MEMORY.delete_session(str(payload.get("session") or ""))
        return {"ok": True, "deleted": n, "message": f"نشست پاک شد ({n} پرامپت)"}
    if action in ("clear", "clear_all"):
        res = MEMORY.clear_history(keep_learning=bool(payload.get("keep_learning", True)))
        return {"ok": True, **res, "message": f"همه‌ی تاریخچه پاک شد ({res['deleted_runs']} پرامپت)"}
    return JSONResponse({"ok": False, "error": "دستور ناشناخته"}, status_code=400)


@app.post("/api/update")
async def api_update(payload: dict = None):
    """🔄 گرفتن نسخهٔ تازه از گیت‌هاب و نصبش (بدون دست‌زدن به .env و داده‌ها)."""
    from mega import updater
    return await asyncio.to_thread(updater.update, bool((payload or {}).get("force")))


@app.get("/api/version")
async def api_version():
    from mega import updater
    return {"ok": True, "version": updater.current_version()}


@app.post("/api/restart")
async def api_restart():
    """ری‌استارت خودکار همین برنامه (ربات متاتریدر دست نمی‌خورد)."""
    from mega import updater
    return await asyncio.to_thread(updater.restart)


@app.get("/api/run/{run_id}")
async def run_detail(run_id: int):
    return {"ok": True, **MEMORY.run_detail(run_id)}


@app.get("/api/leaderboard")
async def leaderboard(task_type: str = ""):
    return {"ok": True, "rows": MEMORY.leaderboard(task_type or None)}


@app.get("/api/workspace")
async def workspace_list(path: str = ""):
    root = WORKSPACE.resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.exists():
        return JSONResponse({"ok": False, "error": "مسیر نامعتبر"}, status_code=400)
    items = []
    for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name)):
        if p.name.startswith("_run_"):
            continue
        items.append({"name": p.name, "dir": p.is_dir(),
                      "size": p.stat().st_size if p.is_file() else None,
                      "path": str(p.relative_to(root))})
    return {"ok": True, "path": path, "items": items}


@app.get("/api/github")
async def github_status():
    """وضعیت اتصال گیت‌هاب (بدون افشای کلید)."""
    from mega.github_tool import GitHub, api_base, token_from_env
    tok = token_from_env()
    out: dict = {"ok": True, "configured": bool(tok), "api": api_base(),
                 "token_hint": (tok[:6] + "…" + tok[-4:]) if len(tok) > 12 else ("دارد" if tok else ""),
                 "env_key": "GITHUB_TOKEN"}
    if tok:
        try:
            gh = GitHub()
            me = await gh.whoami()
            out.update({"login": me.get("login"), "name": me.get("name"),
                        "avatar": me.get("avatar"), "connected": True})
        except Exception as e:  # noqa: BLE001
            out.update({"connected": False, "error": str(e)[:200]})
    return out


@app.post("/api/github/token")
async def github_token(payload: dict):
    """ذخیره‌ی کلید گیت‌هاب + تست واقعی اتصال."""
    from mega.github_tool import save_token, test_token
    tok = (payload.get("token") or "").strip()
    if not tok:
        return JSONResponse({"ok": False, "error": "توکن خالی است"}, status_code=400)
    if payload.get("save", True):
        save_token(tok)
    res = await test_token(tok)
    if payload.get("save", True) and not res.get("ok"):
        from mega.config import save_keys
        save_keys({"GITHUB_TOKEN": ""})          # توکن بی‌اعتبار ذخیره نماند
    return res


@app.get("/api/github/repos")
async def github_repos(limit: int = 30):
    """فهرست مخزن‌های کاربر."""
    from mega.github_tool import GitHub, GitHubError
    try:
        gh = GitHub()
        return {"ok": True, "items": await gh.list_repos(limit=limit)}
    except GitHubError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=400)


@app.post("/api/github/push")
async def github_push(payload: dict):
    """فرستادن پروژه (یا خروجی یک نشست) به گیت‌هاب — با پیشرفت زنده (SSE)."""
    from mega.github_tool import GitHub, GitHubError
    repo = (payload.get("repo") or "").strip()
    if not repo:
        return JSONResponse({"ok": False, "error": "نام مخزن را بده"}, status_code=400)
    target = (payload.get("target") or "project").strip()     # project | session | folder
    session = (payload.get("session") or "").strip()
    folder = (payload.get("folder") or "").strip()
    private = bool(payload.get("private", True))
    message = (payload.get("message") or "MEGA-AI: انتشار خودکار").strip()

    async def gen():
        def send(obj: dict) -> str:
            return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"
        try:
            gh = GitHub()
        except GitHubError as e:
            yield send({"type": "error", "message": str(e)})
            return
        try:
            if target == "session" and session:
                coro = gh.push_session(session, repo, private=private, message=message)
            elif target == "folder" and folder:
                coro = gh.push_folder(WORKSPACE / folder if not Path(folder).is_absolute() else folder,
                                      repo, private=private, message=message)
            else:
                coro = gh.push_project(repo=repo, private=private, message=message)
            task = asyncio.create_task(coro)
            # پیام‌های مرحله‌ای را از طریق یک صف کوچک می‌فرستیم
            while not task.done():
                yield send({"type": "progress", "message": "در حال فرستادن…"})
                await asyncio.sleep(1.2)
            res = await task
            yield send({"type": "done", **res})
        except GitHubError as e:
            yield send({"type": "error", "message": str(e)})
        except Exception as e:  # noqa: BLE001
            yield send({"type": "error", "message": f"{type(e).__name__}: {e}"})
        yield 'data: {"type":"end"}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/system")
async def system_info():
    """وضعیت واقعی همین کامپیوتر: پایتون، ابزارها، کتابخانه‌ها، منابع."""
    import importlib.util
    import platform
    import shutil as _sh

    def has(mod: str) -> bool:
        try:
            return importlib.util.find_spec(mod) is not None
        except Exception:
            return False

    info: dict = {
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "tools": {t: bool(_sh.which(t)) for t in ("ffmpeg", "ffprobe", "git", "node", "npm", "tesseract")},
        "libs": {m: has(m) for m in ("fastapi", "uvicorn", "httpx", "multipart", "PIL",
                                     "pandas", "matplotlib", "openpyxl", "pypdf", "docx",
                                     "arabic_reshaper", "bidi", "psutil", "edge_tts")},
        "workspace": str(WORKSPACE),
        "providers_active": [p.id for p in configured_providers()],
    }
    try:
        import psutil
        info["cpu_count"] = psutil.cpu_count(logical=True)
        info["memory_gb"] = round(psutil.virtual_memory().total / 1024 ** 3, 1)
        info["memory_free_gb"] = round(psutil.virtual_memory().available / 1024 ** 3, 1)
        info["disk_free_gb"] = round(psutil.disk_usage(str(WORKSPACE)).free / 1024 ** 3, 1)
    except Exception:
        pass
    missing = [k for k, v in info["tools"].items() if not v]
    tips = []
    if "ffmpeg" in missing:
        tips.append("برای ویدیو: ffmpeg را نصب کن (ویندوز: winget install Gyan.FFmpeg / مک: brew install ffmpeg)")
    for lib, why in (("pandas", "تحلیل داده"), ("matplotlib", "نمودار"), ("pypdf", "خواندن PDF"),
                     ("arabic_reshaper", "متن فارسی در تصویر"), ("psutil", "گزارش منابع سیستم")):
        if not info["libs"].get(lib):
            tips.append(f"برای {why}: pip install {lib if lib != 'arabic_reshaper' else 'arabic-reshaper python-bidi'}")
    info["tips"] = tips
    info["ready"] = info["libs"].get("fastapi") and info["tools"].get("ffmpeg")
    return {"ok": True, **info}


INCEPTION = WORKSPACE.parent / "inception"


@app.get("/api/prompts")
async def prompts():
    """پروژه‌های آماده از پوشه‌ی inception — هر کدام یک پرامپت بزرگِ قابل‌کپی."""
    items = []
    for f in sorted(INCEPTION.glob("*.md")):
        if f.name.lower() == "readme.md":
            continue
        raw = f.read_text(encoding="utf-8", errors="replace")
        title = ""
        for line in raw.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        blocks = re.findall(r"```(?:\w*)\n(.*?)```", raw, re.S)
        prompt = max(blocks, key=len).strip() if blocks else raw.strip()
        mode = "agent" if "جواب دقیق" not in raw else "panel"
        items.append({"id": f.stem, "title": title or f.stem, "file": f.name,
                      "prompt": prompt[:6000], "mode": mode,
                      "hint": (re.search(r"> روش پیشنهادی: (.+)", raw) or [None, "🛠 انجامش بده"])[1]})
    return {"ok": True, "items": items,
            "note": "این‌ها «پرامپت‌های بزرگ» هستند: در پنل بچسبان و «انجامش بده» را بزن."}


@app.get("/api/prompts/{pid}")
async def prompt_one(pid: str):
    f = INCEPTION / f"{re.sub(r'[^A-Za-z0-9_-]', '', pid)}.md"
    if not f.is_file():
        return JSONResponse({"ok": False, "error": "پروژه پیدا نشد"}, status_code=404)
    return {"ok": True, "text": f.read_text(encoding="utf-8", errors="replace")}


@app.post("/api/upload")
async def upload(request: Request):
    """آپلود واقعی فایل کاربر (تصویر/CSV/کد/سند/صدا/هرچیز) → ذخیره در پوشه‌ی نشست.

    ۱) اگر فایل تحویل بگیرد و سپس فایل‌های دیگر با کد ۲۰۰ برگردند، آن‌ها را با آماده‌ی «/api/uploaded_files?session=…» ببینید.
    """
    from mega.analyze import kind_of
    sess = re.sub(r"[^A-Za-z0-9_-]", "_", (request.query_params.get("session") or "uploads"))
    sdir = WORKSPACE / sess / "uploads"
    sdir.mkdir(parents=True, exist_ok=True)
    form = await request.form()
    saved: list[dict] = []
    for key, value in form.multi_items():
        fname = getattr(value, "filename", None) or ""
        data = getattr(value, "file", None)
        if not fname or data is None:
            continue
        safe = re.sub(r"[^\w\u0600-\u06FF.\-() ]+", "_", Path(fname).name)[:120] or "file"
        dest = sdir / safe
        n = 1
        while dest.exists():
            dest = sdir / f"{Path(safe).stem}_{n}{Path(safe).suffix}"
            n += 1
        raw = await value.read()
        dest.write_bytes(raw)
        # پیش‌تحلیل سریع تا کاربر بلافاصله ببیند چه چیزی گرفته‌ایم
        quick = {}
        try:
            from mega.analyze import analyze_image_local, kind_of as _k
            if _k(dest) == "image":
                quick = analyze_image_local(dest)
        except Exception:
            pass
        saved.append({"name": dest.name, "path": str(dest.relative_to(WORKSPACE)),
                      "abs": str(dest), "size": len(raw), "kind": kind_of(dest),
                      "url": f"/files/{sess}/uploads/{dest.name}", "quick": quick})
    return {"ok": bool(saved), "session": sess, "saved": saved,
            "count": len(saved), "upload_dir": str(sdir)}


@app.get("/api/uploads")
async def list_uploads(session: str = ""):
    """فایل‌های آپلودی یک نشست (یا همه)."""
    from mega.analyze import kind_of
    root = WORKSPACE
    targets = [root / re.sub(r"[^A-Za-z0-9_-]", "_", session) / "uploads"] if session else \
              list(root.glob("*/uploads"))
    items = []
    for d in targets:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir(), key=lambda x: -x.stat().st_mtime):
            if f.is_file() and not f.name.startswith("."):
                items.append({"name": f.name, "session": d.parent.name, "kind": kind_of(f),
                              "size": f.stat().st_size, "path": str(f.relative_to(root)),
                              "url": f"/files/{f.relative_to(root)}",
                              "mtime": f.stat().st_mtime})
    return {"ok": True, "items": items[:200]}


@app.post("/api/analyze")
async def analyze_uploaded(payload: dict):
    """تحلیل کامل یک فایل آپلودی یا ساخته‌شده (تصویر/داده/کد/متن/سند/صدا/ویدیو)."""
    from mega.analyze import analyze_file
    raw = (payload.get("path") or "").strip()
    target = (WORKSPACE / raw) if raw and not Path(raw).is_absolute() else Path(raw)
    if not raw or not target.is_file():
        return JSONResponse({"ok": False, "error": "فایل پیدا نشد"}, status_code=400)
    res = await analyze_file(target, question=str(payload.get("question") or ""),
                             settings=STATE["settings"], use_model=bool(payload.get("use_model", True)))
    if res.get("charts"):
        res["chart_urls"] = [f"/files/{Path(c).relative_to(WORKSPACE)}" for c in res["charts"]]
    return res


@app.get("/api/workspace/file")
async def workspace_file(path: str):
    root = WORKSPACE.resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        return JSONResponse({"ok": False, "error": "فایل نامعتبر"}, status_code=400)
    return {"ok": True, "path": path, "content": target.read_text(encoding="utf-8", errors="replace")[:200_000]}


@app.post("/api/run")
async def run(payload: dict, request: Request):
    """اجرای پرامپت با استریم زنده‌ی همه‌ی مراحل."""
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"ok": False, "error": "پرامپت خالی است"}, status_code=400)
    session_id = payload.get("session_id") or f"s-{uuid.uuid4().hex[:8]}"
    mode = payload.get("mode") or "panel"
    forced = payload.get("models") or None
    s = STATE["settings"]
    for k in ("use_tools", "verify", "panel_size", "max_tool_rounds", "stream", "critique_rounds"):
        if k in payload:
            try:
                cur = getattr(s, k)
                if isinstance(cur, bool):
                    setattr(s, k, bool(payload[k]))
                elif isinstance(cur, (int, float)) and not isinstance(cur, bool):
                    setattr(s, k, type(cur)(payload[k]))
                else:
                    setattr(s, k, payload[k])
            except (TypeError, ValueError):
                pass
    MEMORY.ensure_session(session_id, prompt[:60])
    hist = MEMORY.history(session_id) if payload.get("remember", True) else []
    orch = Orchestrator(s, MEMORY)

    async def gen():
        yield f"data: {json.dumps({'type':'session','session_id':session_id}, ensure_ascii=False)}\n\n"
        try:
            async for ev in orch.run_stream(prompt, session_id=session_id, mode=mode,
                                            forced_models=forced, history=hist):
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type':'error','message':f'{type(e).__name__}: {e}'}, ensure_ascii=False)}\n\n"
        yield "data: {\"type\":\"end\"}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform",
                                      "Connection": "keep-alive", "X-Accel-Buffering": "no"})




# ════════════════════════════════════════════ عامل خودمختار
@app.post("/api/agent")
async def agent_run(payload: dict, request: Request):
    """اجرای یک خواسته با کارگزار مطلق — استریم زنده‌ی گام‌ها و ابزارها."""
    goal = (payload.get("goal") or payload.get("prompt") or "").strip()
    if not goal:
        return JSONResponse({"ok": False, "error": "خواسته خالی است"}, status_code=400)
    session_id = payload.get("session_id") or f"ag-{uuid.uuid4().hex[:8]}"
    mode = payload.get("mode") or "agent"
    MEMORY.ensure_session(session_id, goal[:60])
    hist = MEMORY.history(session_id) if payload.get("remember", True) else []
    ag = MegaAgent(STATE["settings"], MEMORY)

    async def gen():
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        try:
            async for ev in ag.run_stream(goal, session_id=session_id, mode=mode, history=hist):
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': f'{type(e).__name__}: {e}'}, ensure_ascii=False)}\n\n"
        yield 'data: {"type":"end"}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform",
                                      "X-Accel-Buffering": "no"})


# ════════════════════════════════════════════ فایل‌های ساخته‌شده
@app.get("/files/{path:path}")
async def files(path: str, dl: int = 0):
    """فایل‌های ساخته‌شده.

    پیش‌فرض: داخل خود برنامه نمایش داده می‌شوند (HTML در iframe، عکس/ویدیو/صدا در پخش‌کننده).
    با dl=1 : به‌صورت دانلود فرستاده می‌شوند.
    """
    rel = re.sub(r"^[/\\]+", "", str(path or ""))
    roots = [WORKSPACE.resolve(), Path(__file__).resolve().parent]      # ساخته‌ها + خود برنامه
    target = None
    for root in roots:
        cand = (root / rel).resolve()
        if not str(cand).startswith(str(root)) or not cand.is_file():
            continue
        inner = str(cand.relative_to(root)).replace("\\", "/").lower()
        if inner.split("/")[0] in (".env", "data", ".git", ".venv", "node_modules", ".arena", "logs"):
            continue                                                     # رمزها و داده‌های خصوصی
        target = cand
        break
    if target is None:
        return JSONResponse({"ok": False, "error": "فایل پیدا نشد",
                             "hint": "نام فایل را جست‌وجو کن"}, status_code=404)
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
               "X-Frame-Options": "SAMEORIGIN"}                          # اگرrame داخل خود برنامه
    if int(dl or 0):
        return FileResponse(target, filename=target.name, headers=headers)
    if target.suffix.lower() in (".html", ".htm"):
        return FileResponse(target, media_type="text/html; charset=utf-8", headers=headers)
    return FileResponse(target, headers=headers)      # inline → در برنامه باز می‌شود


@app.get("/api/find-file")
async def find_file(name: str = "", limit: int = 24):
    """فایل را بر اساس نام پیدا می‌کند (وقتی آدرس اشتباه بوده یا نام کوتاه داده شده)."""
    q = (name or "").strip().lower()
    if not q:
        return {"ok": True, "items": []}
    stem = Path(q).stem
    out = []
    for root in (WORKSPACE, Path(__file__).resolve().parent):
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*"), key=lambda x: -x.stat().st_mtime if x.is_file() else 0):
            try:
                if not p.is_file():
                    continue
                rel = p.relative_to(root).as_posix()
            except (ValueError, OSError):
                continue
            if rel.split("/")[0] in (".env", "data", ".git", ".venv", "node_modules", ".arena", "logs"):
                continue
            low = p.name.lower()
            if q == low or (stem and stem == p.stem.lower()) or (len(q) >= 3 and (q in low or low in q)):
                out.append({"name": p.name, "path": rel, "size": p.stat().st_size,
                            "url": f"/files/{rel}"})
                if len(out) >= max(1, min(60, int(limit))):
                    return {"ok": True, "items": out}
    return {"ok": True, "items": out}


@app.post("/api/quick")
async def quick_mode(payload: dict):
    """حالت ⚡ سریع: مدل سبک‌تر + گام‌های کمتر → جواب زودتر می‌رسد."""
    s = STATE["settings"]
    on = bool(payload.get("on", True))
    s.fast_mode = on
    if on:
        s.model_tier = "cheap"
        s.agent_max_steps = 8
        s.max_tool_rounds = 1
        s.panel_size = min(int(s.panel_size or 2), 2)
    else:
        s.model_tier = "max"
        s.agent_max_steps = 24
        s.max_tool_rounds = 3
        s.panel_size = max(int(s.panel_size or 4), 4)
    return {"ok": True, "fast_mode": s.fast_mode,
            "settings": {k: getattr(s, k) for k in ("model_tier", "agent_max_steps",
                                                    "max_tool_rounds", "panel_size", "fast_mode")}}


@app.get("/api/artifacts")
async def artifacts(session: str = ""):
    root = WORKSPACE
    bases = [root / session] if session else [p for p in root.iterdir() if p.is_dir()]
    items = []
    for base in bases:
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and not p.name.startswith(("_run_", "scene", "clip")):
                items.append({"path": str(p.relative_to(root)), "name": p.name,
                              "size": p.stat().st_size, "mtime": p.stat().st_mtime,
                              "url": f"/files/{p.relative_to(root)}",
                              "session": base.name})
    items.sort(key=lambda x: -x["mtime"])
    return {"ok": True, "items": items[:300]}


# ════════════════════════════════════════════ کارخانه‌ی محتوا
@app.get("/api/media/options")
async def media_options():
    return {"ok": True, "themes": list(THEMES), "voices": VOICES,
            "presets": ["تبلیغ ویدیویی", "ویدیو آموزشی", "معرفی محصول", "پست اینستاگرام"]}


@app.post("/api/media/video")
async def media_video(payload: dict):
    """ساخت ویدیو/تبلیغ. body: {kind: ad|video, topic|scenes, ratio, theme, voice, music, brand}"""
    kind = payload.get("kind", "ad")
    sdir = WORKSPACE / (payload.get("session_id") or f"media-{uuid.uuid4().hex[:6]}")
    sdir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w\-]", "_", (payload.get("topic") or "video"))[:40] or "video"
    out = sdir / f"{name}_{int(time.time())}.mp4"
    if kind == "ad":
        res = await make_ad(payload.get("topic") or "محصول تو", out,
                            ratio=payload.get("ratio", "9:16"),
                            theme=payload.get("theme", "طلایی لوکس"),
                            voice=payload.get("voice", "fa-IR-FaridNeural"),
                            brand=payload.get("brand", ""),
                            music=bool(payload.get("music", True)))
    else:
        scenes = payload.get("scenes") or []
        if not scenes:
            return JSONResponse({"ok": False, "error": "scenes لازم است"}, status_code=400)
        res = await make_video(scenes, out, ratio=payload.get("ratio", "9:16"),
                               theme=payload.get("theme", "بنفش شب"),
                               voice=payload.get("voice", "fa-IR-DilaraNeural"),
                               subtitles=bool(payload.get("subtitles", True)),
                               music=bool(payload.get("music", False)),
                               brand=payload.get("brand", ""))
    if res.get("ok"):
        res["url"] = f"/files/{out.relative_to(WORKSPACE)}"
        res["session"] = sdir.name
    return res


@app.post("/api/media/image")
async def media_image(payload: dict):
    sdir = WORKSPACE / (payload.get("session_id") or f"media-{uuid.uuid4().hex[:6]}")
    sdir.mkdir(parents=True, exist_ok=True)
    out = sdir / f"poster_{int(time.time())}.png"
    p = make_image(out, payload.get("title", ""), payload.get("lines"),
                   theme=payload.get("theme", "بنفش شب"), ratio=payload.get("ratio", "9:16"),
                   subtitle=payload.get("subtitle", ""), badge=payload.get("badge", ""),
                   footer=payload.get("footer", ""))
    return {"ok": True, "path": p, "url": f"/files/{out.relative_to(WORKSPACE)}"}


@app.post("/api/voice/tts")
async def voice_tts(payload: dict):
    text = (payload.get("text") or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "متن خالی است"}, status_code=400)
    sdir = WORKSPACE / "voice"
    out = sdir / f"tts_{int(time.time())}.mp3"
    res = await tts(text, out, voice=payload.get("voice") or "fa-IR-DilaraNeural")
    if res.get("ok"):
        res["url"] = f"/files/{out.relative_to(WORKSPACE)}"
    return res


@app.post("/api/voice/stt")
async def voice_stt(request: Request):
    """آپلود فایل صوتی (multipart، فیلد file) و تبدیل به متن."""
    form = await request.form()
    up = form.get("file")
    if up is None:
        return JSONResponse({"ok": False, "error": "فایل صوتی لازم است"}, status_code=400)
    sdir = WORKSPACE / "voice"
    sdir.mkdir(parents=True, exist_ok=True)
    dest = sdir / f"in_{int(time.time())}_{getattr(up, 'filename', 'audio.webm')}"
    dest.write_bytes(await up.read())
    return await stt(dest)


# ════════════════════════════════════════════ مهارت‌ها و کتابخانه‌ها
@app.get("/api/skills")
async def skills_list():
    return {"ok": True, "skills": installed_skills(),
            "update_targets": ["pip: --upgrade", "npm", "requirements.txt"]}


@app.post("/api/skills")
async def skills_install(payload: dict):
    action = payload.get("action", "install")
    sdir = WORKSPACE / "_system"
    box = SkillBox(sdir)
    if action == "install":
        out = await box.run("install_skill", {"source": payload.get("source", ""),
                                              "name": payload.get("name", "")})
    elif action == "pip":
        out = await box.run("pip", {"packages": payload.get("source", ""),
                                    "upgrade": bool(payload.get("upgrade", True))})
    elif action == "update":
        out = await update_libraries()
    elif action == "npm":
        out = await box.run("npm", {"command": payload.get("source", "install -g npm@latest")})
    else:
        out = "[action نامعتبر]"
    return {"ok": True, "output": out, "skills": installed_skills()}


# ════════════════════════════════════════════ دستیار تلگرام
TG: dict[str, Any] = {"bot": None, "task": None}


@app.get("/api/telegram")
async def telegram_status():
    b: TelegramBot | None = TG.get("bot")
    me = None
    if b:
        r = await b.call("getMe")
        me = (r.get("result") or {}).get("username")
    return {"ok": True, "running": bool(b and b.running), "username": me,
            "token_set": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
            "stats": (b.stats if b else {})}


@app.post("/api/telegram")
async def telegram_ctl(payload: dict):
    action = payload.get("action", "status")
    token = (payload.get("token") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if action == "stop":
        b: TelegramBot | None = TG.get("bot")
        if b:
            b.stop()
            TG["bot"] = None
        return {"ok": True, "running": False}
    if action != "start":
        return await telegram_status()
    if not token:
        return JSONResponse({"ok": False, "error": "توکن ربات لازم است"}, status_code=400)
    if TG.get("bot") and TG["bot"].running:
        return {"ok": True, "running": True, "note": "از قبل فعال بود"}
    bot = TelegramBot(token, allow_all=STATE["settings"].telegram_allow_all)
    me = await bot.call("getMe")
    if not me.get("ok"):
        return JSONResponse({"ok": False, "error": f"توکن نامعتبر: {me.get('error', me)}"},
                            status_code=400)
    save_keys({"TELEGRAM_BOT_TOKEN": token})
    TG["bot"] = bot
    TG["task"] = asyncio.create_task(bot.poll_forever())
    return {"ok": True, "running": True, "username": (me.get("result") or {}).get("username"),
            "link": f"https://t.me/{(me.get('result') or {}).get('username')}"}




# ════════════════════════════════════════════ راه‌اندازی آسان (ایران)
@app.get("/api/gateways")
async def gateways():
    """فهرست پرووایدرها با توضیح فارسی، لینک کلید و وضعیت."""
    from mega.config import PROVIDERS
    out = []
    for pid, p in PROVIDERS.items():
        out.append({
            "id": pid, "label": p.label, "iran_friendly": p.iran_friendly,
            # «configured» یعنی کلید واقعی کاربر (کلید حالت نمایشی شمرده نمی‌شود)
            "configured": p.configured and bool(p.real_key), "env_key": p.env_key, "signup": p.signup,
            # در حالت نمایشی، آدرس داخلیِ پل نمایشی را نشان نده؛ آدرس واقعی سرویس مهم است
            "base_url": (getattr(p, "base_url_original", None) or p.base_url),
            "models": p.default_models[:6],
            "demo_bridge": bool(getattr(p, "base_url_original", None)),
            "docs": "مستقیم از ایران، بدون فیلترشکن" if p.iran_friendly else "نیازمند پروکسی/فیلترشکن",
        })
    out.sort(key=lambda x: (not x["iran_friendly"], not x["configured"]))
    return {"ok": True, "gateways": out,
            "settings": {k: getattr(STATE["settings"], k) for k in
                         ("proxy", "proxy_scope", "model_tier", "auto_fallback", "panel_size")}}


@app.post("/api/test")
async def test_conn(payload: dict):
    """تست اتصال یک پرووایدر با کلید/آدرس دلخواه (بدون ذخیره)."""
    pid = payload.get("provider") or "avalai"
    res = await test_provider(pid, key=(payload.get("key") or "").strip() or None,
                              base_url=(payload.get("base_url") or "").strip() or None,
                              model=(payload.get("model") or "").strip() or None,
                              settings=STATE["settings"])
    return res


@app.post("/api/setup")
async def setup(payload: dict):
    """ذخیره‌ی تنظیمات اتصال: کلید پرووایدر، پروکسی، سطح قدرت، آدرس سفارشی."""
    from mega import demo_model
    from mega.config import PROVIDERS
    pairs: dict[str, str] = {}
    pid = (payload.get("provider") or "").strip()
    key = (payload.get("key") or "").strip()
    if pid and key:
        p = PROVIDERS.get(pid)
        if p:
            pairs[p.env_key] = key
            if pid == "custom":
                pairs["CUSTOM_BASE_URL"] = (payload.get("base_url") or "").strip()
                ms = (payload.get("models") or "").strip()
                if ms:
                    pairs["CUSTOM_MODELS"] = ms
    if pairs:
        save_keys(pairs)
    s = STATE["settings"]
    if payload.get("tier") is not None and payload.get("model_tier") is None:
        payload["model_tier"] = payload["tier"]        # پنل ساده «tier» می‌فرستد
    for k, cast in (("proxy", str), ("proxy_scope", str), ("model_tier", str)):
        if payload.get(k) is not None:
            setattr(s, k, cast(payload[k]))
    if payload.get("auto_fallback") is not None:
        s.auto_fallback = bool(payload["auto_fallback"])
    if payload.get("panel_size"):
        s.panel_size = max(1, min(8, int(payload["panel_size"])))
    # آدرس سفارشی: بلافاصله در همان اجرا اعمال می‌شود (custom همیشه، بقیه با apply_base)
    from mega.config import PROVIDERS as _P
    base = (payload.get("base_url") or "").strip()
    if pid in _P and base and (pid == "custom" or payload.get("apply_base")):
        _P[pid].custom_base = base.rstrip("/")
    if pid == "custom" and (_P["custom"].custom_base in (None, "", "https://example.com/v1")):
        _P["custom"].custom_base = None
    if pid == "custom":
        ms = [m.strip() for m in (payload.get("models") or "").split(",") if m.strip()]
        if ms:
            _P["custom"].default_models = ms
    if has_real_keys():
        demo_model.disable()
    clear_cache()
    from mega.config import configured_providers as _cp
    return {"ok": True, "active": [p.id for p in _cp()], "providers": key_status(),
            "settings": {k: getattr(s, k) for k in ("proxy", "proxy_scope", "model_tier",
                                                    "auto_fallback", "panel_size")}}


@app.get("/api/diagnose")
async def diagnose(chat: bool = False):
    """سلامت همه‌ی پرووایدرها + پیشنهاد بهترین گزینه."""
    rows = await health_check_all(STATE["settings"], chat_test=chat)
    best = next((r for r in rows if r.get("ok")), None)
    return {"ok": True, "results": rows,
            "best": best, "advice": ("اتصال برقرار است ✅" if best else
                                     "هیچ پرووایدری جواب نداد — کلید را بررسی کن یا از گیت‌وی ایرانی "
                                     "(AvalAI / GapGPT / MetisAI) استفاده کن.")}


@app.get("/api/simple/chat")
async def simple_chat(text: str = "", session: str = "ساده", tier: str = ""):
    """گفتگوی ساده و سریع با یک مدل قوی — استریم توکن‌به‌توکن."""
    from mega.providers import chat, resolve_role
    if not text.strip():
        return JSONResponse({"ok": False, "error": "متن خالی است"}, status_code=400)
    s = STATE["settings"]
    if tier:
        s.model_tier = tier
    spec = (await resolve_role("judge", 0.5, 3000, settings=s)
            or await resolve_role("expert", 0.5, 3000, settings=s))
    if not spec:
        return JSONResponse({"ok": False, "error": "هیچ مدلی در دسترس نیست — کلید API بده."}, status_code=400)
    hist = MEMORY.history(session, 6)
    msgs = [{"role": "system", "content": "تو دستیار فارسی‌زبان و دقیقی هستی. کوتاه، روشن و کاربردی جواب بده. "
                                         "اگر کد لازم است، کد کامل و اجراشدنی بده."}]
    for h in hist:
        msgs.append({"role": "user", "content": (h.get("prompt") or "")[:800]})
        msgs.append({"role": "assistant", "content": (h.get("final") or "")[:1200]})
    msgs.append({"role": "user", "content": text})

    async def gen():
        yield f"data: {json.dumps({'type': 'model', 'name': spec.name, 'provider': spec.provider}, ensure_ascii=False)}\n\n"
        q: asyncio.Queue = asyncio.Queue()
        full: list[str] = []

        def on_delta(t: str) -> None:
            full.append(t)
            q.put_nowait(t)

        task = asyncio.create_task(chat(spec, msgs, s, on_delta))
        while not task.done() or not q.empty():
            try:
                t = await asyncio.wait_for(q.get(), timeout=0.25)
                yield f"data: {json.dumps({'type': 'delta', 'text': t}, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                continue
        r = await task
        if not r.ok:
            yield f"data: {json.dumps({'type': 'error', 'message': r.error}, ensure_ascii=False)}\n\n"
        else:
            MEMORY.ensure_session(session, text[:60])
            run_id = MEMORY.start_run(session, text, "chat", "simple", {"model": spec.id})
            MEMORY.add_stage(run_id, "chat", r.model or spec.model, r.provider or spec.provider,
                             "".join(full), r.seconds, True, r.tokens)
            MEMORY.finish_run(run_id, "".join(full))
        yield f"data: {json.dumps({'type': 'end', 'text': ''.join(full), 'seconds': r.seconds}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform",
                                      "X-Accel-Buffering": "no"})


# ═══════════════ v9.9 │ نگهداری خودکار: پشتیبان، سلامت، PWA، اطلاع تلگرام ═══════════════
_START_TS = time.time()


def _env_num(name: str, default: float) -> float:
    try:
        return float((os.environ.get(name) or "").strip() or default)
    except Exception:  # noqa: BLE001
        return default


@app.get("/manifest.webmanifest")
async def pwa_manifest():
    """فایل «نصب روی گوشی» تا اپ روی صفحهٔ اصلی موبایل آیکون بگیرد."""
    target = WEB_DIR / "manifest.webmanifest"
    if not target.is_file():
        return JSONResponse({"ok": False, "error": "manifest نیست"}, status_code=404)
    return FileResponse(target, media_type="application/manifest+json")


@app.get("/sw.js")
async def pwa_sw():
    """سرویس‌ورکر (شبکه‌اول) — اپ موبایل مثل یک برنامهٔ واقعی باز می‌شود."""
    target = WEB_DIR / "sw.js"
    if not target.is_file():
        return JSONResponse({"ok": False, "error": "sw.js نیست"}, status_code=404)
    return FileResponse(target, media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/api/health/report")
async def api_health_report():
    """نتیجهٔ آخرین تست خودکار (هر چند ساعت یک‌بار خودش می‌گیرد)."""
    hf = ROOT / "data" / "health.json"
    if not hf.is_file():
        return {"ok": True, "report": None, "note": "اولین تست خودکار چند لحظه بعد از روشن شدن انجام می‌شود"}
    try:
        return {"ok": True, "report": json.loads(hf.read_text(encoding="utf-8"))}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)[:120]}, status_code=500)


@app.get("/api/backup/list")
async def api_backup_list():
    from mega import backup as _bk
    return {"ok": True, "rows": _bk.list_backups()}


@app.post("/api/backup/run")
async def api_backup_run(payload: dict = None):
    """پشتیبان بساز و ذخیره کن (در پوشهٔ backups)."""
    from mega import backup as _bk
    full = bool((payload or {}).get("full"))
    return await asyncio.to_thread(_bk.make_backup, full, "manual")


@app.get("/api/backup/download")
async def api_backup_download(full: int = 0):
    """پشتیبان تازه بساز و همین حالا برای دانلود بفرست."""
    from mega import backup as _bk
    res = await asyncio.to_thread(_bk.make_backup, bool(full), "download")
    return FileResponse(res["path"], filename=res["name"], media_type="application/zip")


@app.get("/api/backup/file/{name}")
async def api_backup_file(name: str):
    from mega import backup as _bk
    target = _bk.BACKUP_DIR / Path(name).name
    if not target.is_file():
        return JSONResponse({"ok": False, "error": "پشتیبان پیدا نشد"}, status_code=404)
    return FileResponse(target, filename=target.name, media_type="application/zip")


@app.get("/api/selfcare")
async def api_selfcare():
    """وضعیت نگهداری خودکار برای داشبورد: بالابودن، آخرین تست، آخرین پشتیبان."""
    from mega import backup as _bk
    hf = ROOT / "data" / "health.json"
    last_health = None
    if hf.is_file():
        try:
            last_health = json.loads(hf.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            last_health = None
    phone = ""
    pf = ROOT / "PORT.txt"
    if pf.is_file():
        for line in pf.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("PHONE="):
                phone = line.split("=", 1)[1].strip()
    return {"ok": True, "version": APP_VERSION, "ts_start": int(_START_TS),
            "uptime": int(time.time() - _START_TS), "port": _listen_port(), "phone": phone,
            "health": last_health, "backup": _bk.last(),
            "backup_hours": _env_num("MEGA_BACKUP_HOURS", 24.0),
            "health_hours": _env_num("MEGA_HEALTH_HOURS", 6.0),
            "telegram": bool((os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip())}


async def _health_loop() -> None:
    """هر چند ساعت خودش تست کامل می‌گیرد و نتیجه را در data/health.json می‌نویسد."""
    await asyncio.sleep(max(5.0, _env_num("MEGA_HEALTH_DELAY", 120.0)))
    while True:
        t0 = time.time()
        try:
            data = await selftest(deep=0)
            sm = data.get("summary", {})
            rep = {"when": data.get("checked_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
                   "ts": int(time.time()), "version": APP_VERSION,
                   "ok": sm.get("ok", 0), "fail": sm.get("fail", 0), "skip": sm.get("skip", 0),
                   "verdict": data.get("verdict", ""), "seconds": round(time.time() - t0, 1),
                   "fails": [it.get("name") for sec in data.get("sections", [])
                             for it in sec.get("items", []) if it.get("ok") is False][:12]}
            (ROOT / "data").mkdir(parents=True, exist_ok=True)
            (ROOT / "data" / "health.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                                        encoding="utf-8")
            print(f"[health] {rep['ok']}✅ / {rep['fail']}❌ / {rep['skip']}⚪  ({rep['seconds']}s)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[health] تست خودکار نشد: {type(e).__name__}", flush=True)
        await asyncio.sleep(max(900.0, _env_num("MEGA_HEALTH_HOURS", 6.0) * 3600))


async def _backup_loop() -> None:
    """پشتیبان خودکار دوره‌ای (پیش‌فرض هر ۲۴ ساعت)."""
    from mega import backup as _bk
    hours = _env_num("MEGA_BACKUP_HOURS", 24.0)
    if hours <= 0:
        print("[backup] پشتیبان خودکار خاموش است (MEGA_BACKUP_HOURS=0)", flush=True)
        return
    await asyncio.sleep(45)
    while True:
        try:
            if _bk.due(hours):
                res = await asyncio.to_thread(_bk.make_backup, False, "auto")
                print(f"[backup] {res['name']}  ({res['files']} فایل · {res['bytes'] / 1024:.0f}KB)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[backup] نشد: {type(e).__name__}", flush=True)
        await asyncio.sleep(1800)


async def _boot_notify() -> None:
    """«سرور روشن شد» را در تلگرام می‌فرستد (اگر TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID بگذاری)."""
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not (token and chat):
        return
    try:
        import httpx
        phone = ""
        pf = ROOT / "PORT.txt"
        if pf.is_file():
            for line in pf.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("PHONE="):
                    phone = line.split("=", 1)[1].strip()
        text = (f"🟢 MehranAiShabestar روشن شد\nنسخه: {APP_VERSION}\n"
                f"آدرس: {phone or ('http://<server-ip>:' + str(_listen_port()))}")
        async with httpx.AsyncClient(timeout=15) as c:
            await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": text})
        print("[telegram] پیام «روشن شد» فرستاده شد ✅", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] اطلاع نرفت: {type(e).__name__}", flush=True)


async def _v99_startup() -> None:
    """نگهداری خودکار در پس‌زمینه: سلامت + پشتیبان + اطلاع تلگرام."""
    for coro in (_health_loop(), _backup_loop(), _boot_notify()):
        try:
            asyncio.create_task(coro)
        except Exception:  # noqa: BLE001
            pass


if hasattr(app, "add_event_handler"):
    app.add_event_handler("startup", _v99_startup)     # نسخه‌های تازه
else:
    app.router.on_startup.append(_v99_startup)         # نسخه‌های قدیمی‌تر



_maybe_bridge()


if __name__ == "__main__":
    import uvicorn
    port = _listen_port()
    host = os.environ.get("MEGA_HOST", "0.0.0.0")
    shown = "localhost" if host in ("127.0.0.1", "localhost") else host
    print(f"\n  MehranAiShabestar آماده است →  http://{shown}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")
