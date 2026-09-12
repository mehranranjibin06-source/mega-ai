"""
MEGA-AI  |  لایه‌ی پرووایدرها (نسخه‌ی ایران)
================================================================
یک واسط یکسان برای همه‌ی مدل‌ها با تمرکز بر «کار کردن از داخل ایران»:

• پشتیبانی پروکسی (HTTP/SOCKS5) — فقط برای پرووایدرهای جهانی، گیت‌وی‌های ایرانی مستقیم می‌روند
• تست اتصال با گزارش دقیق خطا (تحریم / کلید / شبکه)
• انتخاب خودکار مدل متناسب با سطح قدرت (قوی‌ترین / متعادل / ارزان)
• اگر یک پرووایدر جواب نداد، خودکار سراغ پرووایدر بعدی می‌رود
• حالت نمایشی (DEMO) وقتی هیچ کلیدی نیست
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from .config import (IRAN_GATEWAYS, PROVIDERS, ROLE_CANDIDATES, SETTINGS, Settings,
                     TIER_PREFS, family_of, pretty_model)

_delta_cb = Callable[[str], None]
_JUNK = ("embed", "whisper", "tts", "image", "vision-only", "rerank", "audio", "realtime",
         "moderation", "-search-preview")


class ModelError(Exception):
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


@dataclass
class ModelSpec:
    provider: str
    model: str
    role: str = "expert"
    label: str = ""
    reason: str = ""                       # توضیح کوتاه که به مدل داده می‌شود
    temperature: float = 0.6
    max_tokens: int = 2048
    fallbacks: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.model}"

    @property
    def name(self) -> str:
        return pretty_model(self.model)

    def to_dict(self) -> dict:
        return {"id": self.id, "provider": self.provider, "model": self.model,
                "name": self.name, "family": family_of(self.model), "role": self.role}


@dataclass
class ChatResult:
    ok: bool
    text: str = ""
    provider: str = ""
    model: str = ""
    tokens: int = 0
    seconds: float = 0.0
    error: str = ""
    demo: bool = False
    via: str = ""            # اگر با پرووایدر دیگری جواب داده شد، نامش


# ─────────────────────────────────────────────────────── کلاینت آگاه به پروکسی
def proxy_for(provider_id: str, settings: Settings) -> Optional[str]:
    """پروکسی مناسب این پرووایدر (یا None)."""
    p = PROVIDERS.get(provider_id)
    px = (settings.proxy or os.environ.get("MEGA_PROXY") or "").strip()
    if not px or not p:
        return None
    if settings.proxy_scope == "all":
        return px
    return None if p.iran_friendly else px          # گیت‌وی ایرانی: مستقیم


def _mk_client(timeout: int, provider_id: str = "", settings: Optional[Settings] = None,
               extra: Optional[dict] = None) -> httpx.AsyncClient:
    s = settings or SETTINGS
    px = proxy_for(provider_id, s) if provider_id else None
    kw: dict[str, Any] = dict(timeout=httpx.Timeout(timeout, connect=25), follow_redirects=True)
    if px:
        kw["proxy"] = px
    if extra:
        kw.update(extra)
    try:
        return httpx.AsyncClient(**kw)
    except Exception:
        # اگر پکیج SOCKS نصب نباشد، بدون پروکسی ادامه بده (خطا گزارش می‌شود)
        kw.pop("proxy", None)
        return httpx.AsyncClient(**kw)


def _headers(p, key: Optional[str] = None) -> dict:
    k = key if key is not None else (p.key or "")
    if p.kind == "anthropic":
        return {"x-api-key": k, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    h = {"Authorization": f"Bearer {k}", "content-type": "application/json"}
    if p.id == "openrouter":
        h["HTTP-Referer"] = "https://mega-ai.local"
        h["X-Title"] = "MEGA-AI Orchestrator"
    return h


# ─────────────────────────────────────────────────────────── کشف لیست مدل‌ها
_model_cache: dict[str, tuple[float, list[str]]] = {}
CACHE_TTL = 900


async def list_models(provider_id: str, client: Optional[httpx.AsyncClient] = None,
                      fresh: bool = False) -> list[str]:
    p = PROVIDERS.get(provider_id)
    if not p or not p.key:
        return []
    cached = _model_cache.get(provider_id)
    if cached and not fresh and time.time() - cached[0] < CACHE_TTL:
        return cached[1]
    own = client is None
    client = client or _mk_client(30, provider_id)
    models: list[str] = []
    try:
        base = p.api_base
        if p.kind == "openai" or p.id == "custom":
            r = await client.get(f"{base}/models", headers={"Authorization": f"Bearer {p.key}"})
            if r.status_code == 200:
                data = r.json()
                models = [m.get("id", "") for m in (data.get("data") or data.get("models") or [])]
        elif p.kind == "gemini":
            r = await client.get(f"{base}/models", params={"key": p.key, "pageSize": 200})
            if r.status_code == 200:
                models = [m.get("name", "").replace("models/", "") for m in r.json().get("models", [])]
        elif p.kind == "anthropic":
            models = list(p.default_models)
    except Exception:
        models = []
    finally:
        if own:
            await client.aclose()
    if not models:
        models = list(p.default_models)
    _model_cache[provider_id] = (time.time(), models)
    return models


def clear_cache() -> None:
    _model_cache.clear()


def _tier_rank(model: str, tier: str) -> int:
    """هرچه کوچک‌تر بهتر — رتبه‌ی مدل در سطح قدرت انتخابی."""
    m = model.lower()
    prefs = TIER_PREFS.get(tier or "balanced", [])
    for i, pref in enumerate(prefs):
        if pref.lower() in m:
            return i
    return len(prefs) + 5


async def _pick_from_provider(provider_id: str, prefs: list[str],
                              exclude: Optional[set[str]] = None,
                              how_many: int = 3, tier: str = "balanced") -> list[str]:
    """بهترین تطابق‌ها را برمی‌گرداند: تطابق دقیق → نسبی → هم‌خانواده → هم‌سطح."""
    exclude = exclude or set()
    available = [m for m in await list_models(provider_id)
                 if f"{provider_id}:{m}" not in exclude and not any(b in m.lower() for b in _JUNK)]
    out: list[str] = []

    def add(m: str) -> None:
        if m and m not in out:
            out.append(m)

    low = {m.lower(): m for m in available}
    tiered = sorted(available, key=lambda m: _tier_rank(m, tier))
    order = list(prefs) + TIER_PREFS.get(tier, [])
    for want in order:
        if want.lower() in low:
            add(low[want.lower()])
    for want in order:
        for m in tiered:
            if want.lower() in m.lower() or m.lower() in want.lower():
                add(m)
    for want in order:
        fam = family_of(want)
        for m in tiered:
            if family_of(m) == fam:
                add(m)
    for m in tiered:
        add(m)
    return out[:how_many]


# ───────────────────────────────────────────────────────── resolve نقش → مدل
async def resolve_role(role: str, temperature: float = 0.6, max_tokens: int = 2048,
                       exclude: Optional[set[str]] = None, offset: int = 0,
                       exclude_providers: Optional[set[str]] = None,
                       settings: Optional[Settings] = None) -> Optional[ModelSpec]:
    s = settings or SETTINGS
    exclude = exclude or set()
    exclude_providers = exclude_providers or set()
    cands = ROLE_CANDIDATES.get(role) or ROLE_CANDIDATES["expert"]
    picked: list[tuple[str, str]] = []
    for pid, prefs in cands:
        p = PROVIDERS[pid]
        if not p.key or pid in exclude_providers:
            continue
        for model in await _pick_from_provider(pid, prefs, exclude, how_many=3, tier=s.model_tier):
            if f"{pid}:{model}" not in exclude:
                picked.append((pid, model))
    if not picked:
        # پرووایدر سفارشی یا هر پرووایدر دیگری که کلید دارد (حتی اگر در فهرست نقش نباشد)
        for pid, p in PROVIDERS.items():
            if not p.key or pid in exclude_providers:
                continue
            prefs = list(p.default_models) + TIER_PREFS.get(s.model_tier, [])
            if pid == "custom":
                from .config import CUSTOM_MODELS
                prefs = CUSTOM_MODELS + prefs
            for model in await _pick_from_provider(pid, prefs, exclude, how_many=2, tier=s.model_tier):
                picked.append((pid, model))
    # مدل‌های هر پرووایدر بر اساس سطح قدرت مرتب شوند
    picked.sort(key=lambda pm: _tier_rank(pm[1], s.model_tier))
    if not picked:
        return None
    pid, model = picked[min(offset, len(picked) - 1)]
    others = [m for q, m in picked if q == pid and m != model]
    return ModelSpec(pid, model, role=role, temperature=temperature,
                     max_tokens=max_tokens, fallbacks=others[:3])


# ───────────────────────────────────────────────────────────── فراخوانی مدل
def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    sys_parts = [m["content"] for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    return "\n\n".join(sys_parts), rest


def _extract(kind: str, data: dict, acc: list[str]) -> None:
    try:
        if kind == "openai":
            ch = (data.get("choices") or [{}])[0]
            txt = (ch.get("delta") or {}).get("content") or ""
            if not txt and isinstance(ch.get("message"), dict):
                txt = ch["message"].get("content") or ""
            if txt:
                acc.append(txt)
        elif kind == "anthropic":
            if data.get("type") == "content_block_delta":
                t = (data.get("delta") or {}).get("text") or ""
                if t:
                    acc.append(t)
        elif kind == "gemini":
            for cand in data.get("candidates", []):
                for part in (cand.get("content") or {}).get("parts", []):
                    if part.get("text"):
                        acc.append(part["text"])
    except Exception:
        pass


def _err_text(r: httpx.Response) -> str:
    try:
        j = r.json()
        msg = j.get("error", j)
        if isinstance(msg, dict):
            msg = msg.get("message") or json.dumps(msg, ensure_ascii=False)
        return f"HTTP {r.status_code}: {str(msg)[:300]}"
    except Exception:
        return f"HTTP {r.status_code}: {r.text[:250]}"


def _hint_for(err: str, provider_id: str) -> str:
    e = (err or "").lower()
    p = PROVIDERS.get(provider_id)
    if any(k in e for k in ("401", "invalid api key", "incorrect api key", "unauthorized",
                            "no api key", "کلید")):
        return "کلید API اشتباه یا منقضی است."
    if any(k in e for k in ("403", "forbidden", "region", "country", "sanction", "unsupported")):
        return ("دسترسی از این منطقه بسته است — یا گیت‌وی ایرانی (AvalAI/GapGPT/MetisAI) استفاده کن، "
                "یا در تنظیمات «پروکسی» را روشن کن.")
    if any(k in e for k in ("timeout", "timed out", "connect", "getaddrinfo", "network",
                            "connection", "ssl", "reset")):
        if p and p.iran_friendly:
            return ("گیت‌وی ایرانی از بیرون ایران بسته است (این پیام طبیعی است اگر سرور خارج از ایران "
                    "باشد). از داخل ایران با اینترنت عادی کار می‌کند؛ اگر آنجا هم وصل نشد، DNS را عوض کن "
                    "(مثلاً 1.1.1.1) یا اینترنت را بررسی کن.")
        return ("اتصال برقرار نشد — اگر سرویس جهانی است، در تنظیمات «پروکسی» را وارد کن "
                "(مثلاً http://127.0.0.1:7890 یا socks5://127.0.0.1:1080).")
    if "429" in e:
        return "محدودیت نرخ درخواست — چند لحظه بعد دوباره امتحان کن."
    if "402" in e or "quota" in e or "insufficient" in e or "balance" in e:
        return "اعتبار حساب تمام شده است."
    if p and p.kind == "gemini" and "404" in e:
        return "نام مدل اشتباه است."
    return ""


async def _call_once(p, model: str, messages: list[dict], spec: ModelSpec, settings: Settings,
                     on_delta: Optional[_delta_cb]) -> tuple[str, int, bool]:
    stream = settings.stream and on_delta is not None
    async with _mk_client(settings.request_timeout, spec.provider, settings) as client:
        base = p.api_base
        if p.kind == "openai":
            url = f"{base}/chat/completions"
            body: dict[str, Any] = {"model": model, "messages": messages,
                                    "temperature": spec.temperature, "max_tokens": spec.max_tokens,
                                    "stream": stream}
            if stream:
                body["stream_options"] = {"include_usage": True}
            return await _sse_call(client, url, _headers(p), body, "openai", on_delta, stream)
        if p.kind == "anthropic":
            sys_prompt, rest = _split_system(messages)
            body = {"model": model, "messages": rest, "max_tokens": spec.max_tokens,
                    "temperature": min(spec.temperature, 1.0), "stream": stream}
            if sys_prompt:
                body["system"] = sys_prompt
            return await _sse_call(client, f"{base}/messages", _headers(p), body,
                                   "anthropic", on_delta, stream)
        if p.kind == "gemini":
            sys_prompt, rest = _split_system(messages)
            contents = [{"role": "model" if m["role"] == "assistant" else "user",
                         "parts": [{"text": m["content"]}]} for m in rest]
            body = {"contents": contents,
                    "generationConfig": {"temperature": spec.temperature,
                                         "maxOutputTokens": spec.max_tokens}}
            if sys_prompt:
                body["systemInstruction"] = {"parts": [{"text": sys_prompt}]}
            verb = "streamGenerateContent?alt=sse" if stream else "generateContent"
            return await _sse_call(client, f"{base}/models/{model}:{verb}",
                                   {"x-goog-api-key": p.key or "", "content-type": "application/json"},
                                   body, "gemini", on_delta, stream)
    raise ModelError("پرووایدر پشتیبانی نمی‌شود")


async def _sse_call(client, url, headers, body, kind, on_delta, stream) -> tuple[str, int, bool]:
    acc: list[str] = []
    tokens = 0
    if not stream:
        r = await client.post(url, headers=headers, json=body)
        if r.status_code >= 400:
            raise ModelError(_err_text(r), r.status_code)
        data = r.json()
        _extract(kind, data, acc)
        tokens = (data.get("usage") or {}).get("total_tokens") or 0
        text = "".join(acc)
        if on_delta and text:
            on_delta(text)
        return text, tokens, False
    async with client.stream("POST", url, headers=headers, json=body) as r:
        if r.status_code >= 400:
            raw = (await r.aread()).decode("utf-8", "ignore")
            raise ModelError(raw[:300] or f"HTTP {r.status_code}", r.status_code)
        async for line in r.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload in ("[DONE]", ""):
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            before = len(acc)
            _extract(kind, data, acc)
            if len(acc) > before and on_delta:
                on_delta(acc[-1])
            u = data.get("usage") or (data.get("usageMetadata") or {})
            if u:
                tokens = u.get("total_tokens") or u.get("totalTokenCount") or tokens
    return "".join(acc), tokens, False


async def _chat_one(spec: ModelSpec, messages: list[dict], settings: Settings,
                    on_delta: Optional[_delta_cb]) -> ChatResult:
    p = PROVIDERS.get(spec.provider)
    if not p or not p.key:
        return await _mock_chat(spec, messages, on_delta)
    models = [spec.model] + [m for m in spec.fallbacks if m != spec.model]
    last_err, t0 = "خطای نامشخص", time.time()
    for idx, model in enumerate(models[:3]):
        for attempt in range(settings.max_retries):
            try:
                text, tokens, demo = await _call_once(p, model, messages, spec, settings, on_delta)
                if not text.strip():
                    raise ModelError("پاسخ خالی برگشت", 0)
                return ChatResult(True, text, spec.provider, model, tokens,
                                  round(time.time() - t0, 2), demo=demo)
            except ModelError as e:
                last_err = str(e)
                if e.status in (400, 404, 422) and idx + 1 < len(models[:3]):
                    break                       # مدل اشتباه → مدل بعدی همین پرووایدر
                if e.status in (429, 500, 502, 503, 529, 0) and attempt + 1 < settings.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 6) + random.random())
                    continue
                break
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
                if attempt + 1 < settings.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 6))
                    continue
                break
    return ChatResult(False, provider=spec.provider, model=spec.model, error=last_err,
                      seconds=round(time.time() - t0, 2))


async def chat(spec: ModelSpec, messages: list[dict], settings: Optional[Settings] = None,
               on_delta: Optional[_delta_cb] = None) -> ChatResult:
    """فراخوانی مدل؛ در صورت شکست، خودکار پرووایدر دیگری را امتحان می‌کند."""
    s = settings or SETTINGS
    res = await _chat_one(spec, messages, s, on_delta)
    if res.ok or not s.auto_fallback or res.demo:
        return res
    tried = {spec.provider}
    for _ in range(2):
        alt = await resolve_role(spec.role or "expert", spec.temperature, spec.max_tokens,
                                 exclude_providers=tried, settings=s)
        if not alt:
            break
        alt.reason = spec.reason
        alt2 = await _chat_one(alt, messages, s, on_delta)
        if alt2.ok:
            alt2.via = f"{spec.provider} → {alt.provider}"
            return alt2
        tried.add(alt.provider)
    return res


# ──────────────────────────────────────────────────────────────── تست اتصال
async def test_provider(provider_id: str, key: Optional[str] = None, base_url: Optional[str] = None,
                        model: Optional[str] = None, settings: Optional[Settings] = None,
                        chat_test: bool = True) -> dict:
    """
    یک پرووایدر را واقعاً امتحان می‌کند: لیست مدل‌ها + یک پیام کوتاه.
    خروجی شامل زمان پاسخ، مدل نمونه و راهنمای رفع خطا.
    """
    s = settings or SETTINGS
    p = PROVIDERS.get(provider_id)
    if not p:
        return {"ok": False, "error": "پرووایدر ناشناخته"}

    import copy as _copy
    test_p = _copy.copy(p)
    if key:
        test_p.key_override = key
    if base_url:
        test_p.custom_base = base_url.rstrip("/")
    elif key:
        # کاربر کلید واقعی داده → آدرس واقعی سرویس را تست کن (نه پل مدل نمایشی)
        test_p.custom_base = getattr(p, "base_url_original", None) or p.base_url
    PROVIDERS_copy = test_p
    t0 = time.time()
    models: list[str] = []

    async with _mk_client(25, provider_id, s) as client:
        try:
            base = PROVIDERS_copy.api_base
            if PROVIDERS_copy.kind == "openai" or provider_id == "custom":
                r = await client.get(f"{base}/models", headers={"Authorization": f"Bearer {PROVIDERS_copy.key}"})
                if r.status_code == 200:
                    data = r.json()
                    models = [m.get("id", "") for m in (data.get("data") or data.get("models") or [])]
                elif r.status_code in (401, 403):
                    err = _err_text(r)
                    return {"ok": False, "stage": "models", "latency_ms": int((time.time() - t0) * 1000),
                            "error": err, "hint": _hint_for(err, provider_id)}
            elif PROVIDERS_copy.kind == "gemini":
                r = await client.get(f"{base}/models", params={"key": PROVIDERS_copy.key, "pageSize": 200})
                if r.status_code == 200:
                    models = [m.get("name", "").replace("models/", "") for m in r.json().get("models", [])]
                elif r.status_code in (400, 401, 403):
                    err = _err_text(r)
                    return {"ok": False, "stage": "models", "latency_ms": int((time.time() - t0) * 1000),
                            "error": err, "hint": _hint_for(err, provider_id)}
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            return {"ok": False, "stage": "network", "latency_ms": int((time.time() - t0) * 1000),
                    "error": err, "hint": _hint_for(err, provider_id)}

    usable = [m for m in models if not any(b in m.lower() for b in _JUNK)] or list(p.default_models)
    pick = model or (sorted(usable, key=lambda m: _tier_rank(m, s.model_tier)) or ["?"])[0]
    result: dict[str, Any] = {
        "ok": True, "provider": provider_id, "provider_label": p.label,
        "iran_friendly": p.iran_friendly, "base_url": PROVIDERS_copy.api_base,
        "models_count": len(usable), "sample_models": usable[:14], "picked": pick,
        "latency_ms": int((time.time() - t0) * 1000),
    }
    if not chat_test:
        return result

    # آزمون واقعی گفتگو
    spec = ModelSpec(provider_id, pick, role="router", temperature=0.1, max_tokens=64)
    PROV_ORIG = PROVIDERS.get(provider_id)
    PROVIDERS[provider_id] = test_p          # موقتاً با کلید/آدرس آزمون
    try:
        r = await _chat_one(spec, [{"role": "user", "content": "فقط بنویس: آماده‌ام ✅"}], s, None)
    finally:
        if PROV_ORIG is not None:
            PROVIDERS[provider_id] = PROV_ORIG
    result["latency_ms"] = int((time.time() - t0) * 1000)
    if r.ok:
        result["reply"] = (r.text or "").strip()[:120]
        result["chat_ok"] = True
    else:
        result["ok"] = False
        result["chat_ok"] = False
        result["error"] = r.error
        result["hint"] = _hint_for(r.error, provider_id)
    return result


async def health_check_all(settings: Optional[Settings] = None, chat_test: bool = False) -> list[dict]:
    """همه‌ی پرووایدرهای دارای کلید را موازی امتحان می‌کند."""
    s = settings or SETTINGS
    ids = [pid for pid, p in PROVIDERS.items() if p.key and pid != "custom"]
    if not ids:
        return []
    res = await asyncio.gather(*[test_provider(pid, settings=s, chat_test=chat_test) for pid in ids],
                               return_exceptions=True)
    out = []
    for pid, r in zip(ids, res):
        out.append(r if isinstance(r, dict) else {"ok": False, "provider": pid, "error": str(r)})
    out.sort(key=lambda x: (not x.get("ok"), x.get("latency_ms", 99999)))
    return out


# ─────────────────────────────────────────────────────────────── حالت نمایشی
_MOCK = {
    "router": "کاربر یک درخواست «{kind}» داده است. نقشه‌ی اجرا: ۱) مشورت چند مدل ۲) نقد متقابل ۳) داوری و سنتز.",
    "expert": "پاسخ آزمایشی (DEMO) از سمت {model}؛ چون کلید API ثبت نشده، تماس واقعی انجام نشد.",
    "critic": "نقد آزمایشی: پاسخ منسجم است ولی به منبع و جزئیات عددی نیاز دارد.",
    "judge": "پاسخ نهایی آزمایشی (DEMO). برای پاسخ واقعی از ترکیب چند هوش، کلید API را در پنل وارد کن.",
    "verifier": "بازبینی آزمایشی: پاسخ با درخواست هم‌راستاست.",
}


async def _mock_chat(spec: ModelSpec, messages: list[dict], on_delta: Optional[_delta_cb]) -> ChatResult:
    tpl = _MOCK.get(spec.role, _MOCK["expert"])
    user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    text = tpl.format(kind="پرسش" if len(user) < 200 else "کار بلند", model=pretty_model(spec.model))
    for word in text.split(" "):
        if on_delta:
            on_delta(word + " ")
        await asyncio.sleep(0.01)
    return ChatResult(True, text, spec.provider, spec.model, 0, round(random.uniform(.3, 1.1), 2), demo=True)
