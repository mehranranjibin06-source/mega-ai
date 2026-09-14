"""
MEGA-AI  |  تنظیمات، کلیدها و رجیستری مدل‌ها
------------------------------------------------
همه‌ی کلیدهای API از فایل .env (یا متغیرهای محیطی) خوانده می‌شوند.
هر پرووایدری که کلید داشته باشد، خودکار وارد «پنل خبرگان» می‌شود.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

APP_VERSION = "7.2"          # نسخهٔ برنامه (در هدر برنامه دیده می‌شود)

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
WORKSPACE = ROOT / "workspace"
DB_PATH = ROOT / "data" / "mega.db"
WEB_DIR = ROOT / "web"

WORKSPACE.mkdir(parents=True, exist_ok=True)
(ROOT / "data").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- .env loader
def load_env() -> None:
    """کلیدها را از .env می‌خواند (متغیرهای محیطی موجود اولویت دارند)."""
    if not ENV_PATH.exists():
        return
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and not os.environ.get(k):
            os.environ[k] = v


def save_keys(pairs: dict[str, str]) -> None:
    """کلیدها را در .env ذخیره و بلافاصله فعال می‌کند."""
    existing: dict[str, str] = {}
    if ENV_PATH.exists():
        for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()
    for k, v in pairs.items():
        v = (v or "").strip()
        if v:
            existing[k] = v
            os.environ[k] = v
        elif k in existing:  # مقدار خالی = حذف کلید
            existing.pop(k, None)
            os.environ.pop(k, None)
    body = "\n".join(f"{k}={v}" for k, v in sorted(existing.items()))
    ENV_PATH.write_text(
        "# MEGA-AI keys — این فایل محرمانه است، جایی آپلودش نکن\n" + body + "\n",
        encoding="utf-8",
    )
    os.chmod(ENV_PATH, 0o600)
    apply_env_bases()


# ---------------------------------------------------------------- providers
IRAN_FRIENDLY = {"avalai", "gapgpt", "metisai", "winkapi", "sinox", "jarvis",
                 "deepseek", "qwen", "moonshot"}


@dataclass
class Provider:
    id: str
    label: str
    kind: str  # openai | anthropic | gemini
    base_url: str
    env_key: str
    default_models: list[str] = field(default_factory=list)
    signup: str = ""
    key_override: Optional[str] = None   # برای حالت نمایشی/پروکسی داخلی
    custom_base: Optional[str] = None    # برای پرووایدر سفارشی

    @property
    def iran_friendly(self) -> bool:
        return self.id in IRAN_FRIENDLY

    @property
    def api_base(self) -> str:
        """آدرس واقعی برای درخواست‌ها (با احترام به تنظیم سفارشی)."""
        if self.custom_base:
            return self.custom_base.rstrip("/")
        return self.base_url

    @property
    def key(self) -> Optional[str]:
        if self.key_override:
            return self.key_override
        return (os.environ.get(self.env_key) or "").strip() or None

    @property
    def real_key(self) -> Optional[str]:
        """فقط کلید واقعی کاربر (بدون override) — برای تشخیص حالت نمایشی."""
        return (os.environ.get(self.env_key) or "").strip() or None

    @property
    def configured(self) -> bool:
        return bool(self.key)


# ترتیب این دیکشنری = ترتیب پیشنهاد در پنل کاربری.
# iran_friendly = از داخل ایران بدون فیلترشکن کار می‌کند.
PROVIDERS: dict[str, Provider] = {
    # ─────────── گیت‌وی‌های ایرانی: بدون فیلترشکن، پرداخت ریالی، همهٔ مدل‌ها ───────────
    "avalai": Provider(
        "avalai", "AvalAI (ایرانی — GPT، Claude، Gemini)", "openai",
        "https://api.avalai.ir/v1", "AVALAI_API_KEY",
        ["gpt-5", "gpt-4.1", "claude-sonnet-4-5", "gemini-2.5-pro", "deepseek-chat", "qwen3-max"],
        "https://avalai.ir",
    ),
    "gapgpt": Provider(
        "gapgpt", "GapGPT (ایرانی — GPT، Claude، Gemini)", "openai",
        "https://api.gapgpt.app/v1", "GAPGPT_API_KEY",
        ["gpt-5", "gpt-4o", "claude-sonnet-4-5", "claude-3-5-sonnet", "gemini-2.5-pro", "deepseek-chat"],
        "https://gapgpt.app/ai-api",
    ),
    "metisai": Provider(
        "metisai", "MetisAI (ایرانی — GPT، Claude، Gemini)", "openai",
        "https://api.metisai.ir/openai/v1", "METIS_API_KEY",
        ["gpt-5", "gpt-4o", "claude-sonnet-4", "claude-3-opus", "gemini-2.5-pro", "deepseek-chat"],
        "https://www.metisai.ir",
    ),
    "winkapi": Provider(
        "winkapi", "WinkAPI (ایرانی — GPT، Claude، Gemini)", "openai",
        "https://api.winkapi.net/v1", "WINK_API_KEY",
        ["gpt-5", "claude-sonnet-4-5", "gemini-2.5-pro", "deepseek-chat"],
        "https://winkapi.net",
    ),
    "sinox": Provider(
        "sinox", "SinoxAPI (ایرانی — ۲۲ مدل برتر)", "openai",
        "https://sinoxapi.com/v1", "SINOX_API_KEY",
        ["gpt-5", "claude-opus-4", "gemini-2.5-pro", "deepseek-chat"],
        "https://sinoxapi.com",
    ),
    "jarvis": Provider(
        "jarvis", "Jarvis (ایرانی — GPT، Claude، Gemini، Grok)", "openai",
        "https://api.jarvis.you/v1", "JARVIS_API_KEY",
        ["GPT_5", "claude-sonnet-4-5", "gemini-2.5-pro", "grok-4", "deepseek-chat"],
        "https://jarvis.you",
    ),
    # ─────────── مدل‌هایی که از ایران مستقیم در دسترس‌اند ───────────
    "deepseek": Provider(
        "deepseek", "DeepSeek (مستقیم از ایران)", "openai", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY",
        ["deepseek-chat", "deepseek-reasoner"],
        "https://platform.deepseek.com/api_keys",
    ),
    "qwen": Provider(
        "qwen", "Qwen / Alibaba (مستقیم از ایران)", "openai",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "QWEN_API_KEY",
        ["qwen3-max", "qwen-max", "qwen-plus", "qwen-turbo", "qwen3-235b-a22b"],
        "https://modelstudio.console.alibabacloud.com",
    ),
    "moonshot": Provider(
        "moonshot", "Kimi / Moonshot (مستقیم از ایران)", "openai",
        "https://api.moonshot.cn/v1", "MOONSHOT_API_KEY",
        ["kimi-k2-0905-preview", "moonshot-v1-128k", "moonshot-v1-32k"],
        "https://platform.moonshot.cn/console/api-keys",
    ),
    # ─────────── پرووایدرهای جهانی (نیازمند پروکسی/فیلترشکن) ───────────
    "openrouter": Provider(
        "openrouter", "OpenRouter (جهانی — با پروکسی)", "openai",
        "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
        ["x-ai/grok-4", "deepseek/deepseek-chat-v3.1", "qwen/qwen3-235b-a22b",
         "meta-llama/llama-3.3-70b-instruct", "google/gemini-2.5-pro"],
        "https://openrouter.ai/keys",
    ),
    "openai": Provider(
        "openai", "OpenAI (GPT)", "openai", "https://api.openai.com/v1", "OPENAI_API_KEY",
        ["gpt-5", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o4-mini"],
        "https://platform.openai.com/api-keys",
    ),
    "anthropic": Provider(
        "anthropic", "Anthropic (Claude)", "anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY",
        ["claude-sonnet-4-5", "claude-sonnet-4-20250514", "claude-3-7-sonnet-latest",
         "claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"],
        "https://console.anthropic.com/settings/keys",
    ),
    "gemini": Provider(
        "gemini", "Google (Gemini)", "gemini", "https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY",
        ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "https://aistudio.google.com/apikey",
    ),
    "groq": Provider(
        "groq", "Groq (جهانی — با پروکسی)", "openai", "https://api.groq.com/openai/v1", "GROQ_API_KEY",
        ["llama-3.3-70b-versatile", "moonshotai/kimi-k2-instruct", "llama-3.1-8b-instant"],
        "https://console.groq.com/keys",
    ),
    "xai": Provider(
        "xai", "xAI (Grok)", "openai", "https://api.x.ai/v1", "XAI_API_KEY",
        ["grok-4", "grok-3", "grok-3-mini"],
        "https://console.x.ai",
    ),
}

# ------------------------------------------------------- انتخاب مدل برای نقش‌ها
# برای هر نقش، به ترتیب اولویت دنبال مدل می‌گردیم؛ اولین مدلی که کلیدش موجود
# و قابل استفاده باشد انتخاب می‌شود. اگر مدلی نبود، از لیست مدل‌های خود پرووایدر
# (auto-discovery) جایگزین انتخاب می‌شود.
# سطح «قدرت» مدل: کاربر می‌تواند قوی‌ترین/متعادل/ارزان را انتخاب کند
TIER_PREFS: dict[str, list[str]] = {
    "max": ["gpt-5", "claude-opus", "claude-sonnet-4-5", "claude-sonnet-4", "gemini-2.5-pro",
            "grok-4", "deepseek-reasoner", "qwen3-max", "kimi-k2"],
    "balanced": ["gpt-4.1", "claude-sonnet", "gemini-2.5-flash", "deepseek-chat",
                 "qwen-plus", "llama-3.3-70b", "gpt-4o"],
    "cheap": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-5-mini", "claude-3-5-haiku", "gemini-2.0-flash",
              "gemini-1.5-flash", "deepseek-chat", "qwen-turbo", "llama-3.1-8b"],
}

# گیت‌وی‌های ایرانی اول فهرست‌اند تا اگر کلیدشان باشد، همه‌ی نقش‌ها با آن‌ها پر شود
IRAN_GATEWAYS = ["avalai", "gapgpt", "metisai", "winkapi", "sinox", "jarvis"]

ROLE_CANDIDATES: dict[str, list[tuple[str, list[str]]]] = {
    "router": [
        ("cloudflare", ["@cf/meta/llama-3.1-8b-instruct-fp8"]),
        ("avalai", ["gpt-5-mini", "gemini-2.5-flash", "gpt-4o-mini", "claude-3-5-haiku", "gpt-5", "claude-sonnet-4-5"]),
        ("gapgpt", ["gpt-4o-mini", "gpt-5-mini", "gpt-4o", "gpt-5", "claude-sonnet-4-5"]),
        ("metisai", ["gpt-4o-mini", "gpt-4o", "gpt-5"]),
        ("winkapi", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
        ("sinox", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
          # تحلیل پرامپت و طراحی نقشه‌ی اجرا  (سریع و ارزان)
        ("gemini", ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]),
        ("openai", ["gpt-4o-mini", "gpt-4.1-mini", "gpt-5-mini"]),
        ("anthropic", ["claude-3-5-haiku-latest"]),
        ("groq", ["llama-3.1-8b-instant"]),
        ("openrouter", ["google/gemini-2.5-flash", "meta-llama/llama-3.3-70b-instruct"]),
        ("deepseek", ["deepseek-chat"]),
    ],
    "judge": [
        ("cloudflare", ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/qwen/qwen2.5-coder-32b-instruct"]),
        ("avalai", ["gpt-5-mini", "gemini-2.5-flash", "gpt-4o-mini", "claude-3-5-haiku", "gpt-5", "claude-sonnet-4-5"]),
        ("gapgpt", ["gpt-4o-mini", "gpt-5-mini", "gpt-4o", "gpt-5", "claude-sonnet-4-5"]),
        ("metisai", ["gpt-4o-mini", "gpt-4o", "gpt-5"]),
        ("winkapi", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
        ("sinox", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
          # داوری و سنتز نهایی (قوی‌ترین مدل)
        ("anthropic", ["claude-sonnet-4-5", "claude-3-7-sonnet-latest", "claude-3-5-sonnet-latest"]),
        ("openai", ["gpt-5", "gpt-4.1", "gpt-4o"]),
        ("gemini", ["gemini-2.5-pro", "gemini-2.5-flash"]),
        ("openrouter", ["x-ai/grok-4", "deepseek/deepseek-chat-v3.1"]),
        ("deepseek", ["deepseek-reasoner", "deepseek-chat"]),
    ],
    "critic": [
        ("cloudflare", ["@cf/meta/llama-3.3-70b-instruct-fp8-fast"]),
        ("avalai", ["gpt-5-mini", "gemini-2.5-flash", "gpt-4o-mini", "claude-3-5-haiku", "gpt-5", "claude-sonnet-4-5"]),
        ("gapgpt", ["gpt-4o-mini", "gpt-5-mini", "gpt-4o", "gpt-5", "claude-sonnet-4-5"]),
        ("metisai", ["gpt-4o-mini", "gpt-4o", "gpt-5"]),
        ("winkapi", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
        ("sinox", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
          # نقد و ارزیابی پاسخ دیگران
        ("openai", ["gpt-5", "gpt-4.1", "gpt-4o"]),
        ("anthropic", ["claude-3-7-sonnet-latest", "claude-3-5-sonnet-latest"]),
        ("gemini", ["gemini-2.5-pro", "gemini-2.5-flash"]),
        ("deepseek", ["deepseek-reasoner", "deepseek-chat"]),
        ("openrouter", ["deepseek/deepseek-chat-v3.1"]),
    ],
    "verifier": [
        ("cloudflare", ["@cf/meta/llama-3.3-70b-instruct-fp8-fast"]),
        ("avalai", ["gpt-5-mini", "gemini-2.5-flash", "gpt-4o-mini", "claude-3-5-haiku", "gpt-5", "claude-sonnet-4-5"]),
        ("gapgpt", ["gpt-4o-mini", "gpt-5-mini", "gpt-4o", "gpt-5", "claude-sonnet-4-5"]),
        ("metisai", ["gpt-4o-mini", "gpt-4o", "gpt-5"]),
        ("winkapi", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
        ("sinox", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
          # بازبینی پاسخ نهایی
        ("gemini", ["gemini-2.5-pro", "gemini-2.5-flash"]),
        ("openai", ["gpt-4.1", "gpt-4o"]),
        ("anthropic", ["claude-3-5-haiku-latest"]),
        ("openrouter", ["x-ai/grok-4", "qwen/qwen3-235b-a22b"]),
    ],
    # اعضای پنل خبرگان از پرووایدرهای متفاوت انتخاب می‌شوند تا خطاها هم‌بسته نشوند
    "expert": [
        ("cloudflare", ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/qwen/qwen2.5-coder-32b-instruct"]),
        ("avalai", ["gpt-5-mini", "gemini-2.5-flash", "gpt-4o-mini", "claude-3-5-haiku", "gpt-5", "claude-sonnet-4-5"]),
        ("gapgpt", ["gpt-4o-mini", "gpt-5-mini", "gpt-4o", "gpt-5", "claude-sonnet-4-5"]),
        ("metisai", ["gpt-4o-mini", "gpt-4o", "gpt-5"]),
        ("winkapi", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
        ("sinox", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
        
        ("openai", ["gpt-5", "gpt-4.1", "gpt-4o"]),
        ("anthropic", ["claude-sonnet-4-5", "claude-3-7-sonnet-latest", "claude-3-5-sonnet-latest"]),
        ("gemini", ["gemini-2.5-pro", "gemini-2.5-flash"]),
        ("openrouter", ["x-ai/grok-4", "deepseek/deepseek-chat-v3.1", "qwen/qwen3-235b-a22b",
                        "meta-llama/llama-3.3-70b-instruct"]),
        ("deepseek", ["deepseek-chat", "deepseek-reasoner"]),
        ("xai", ["grok-4", "grok-3"]),
        ("groq", ["llama-3.3-70b-versatile"]),
    ],
    # «پنل جانشین»: وقتی بیش از یک مدل از یک پرووایدر لازم داریم
    "agent": [
        ("cloudflare", ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/qwen/qwen2.5-coder-32b-instruct"]),
        ("avalai", ["gpt-5-mini", "gemini-2.5-flash", "gpt-4o-mini", "claude-3-5-haiku", "gpt-5", "claude-sonnet-4-5"]),
        ("gapgpt", ["gpt-4o-mini", "gpt-5-mini", "gpt-4o", "gpt-5", "claude-sonnet-4-5"]),
        ("metisai", ["gpt-4o-mini", "gpt-4o", "gpt-5"]),
        ("winkapi", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
        ("sinox", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
          # کارگزار خودمختار: قوی‌ترین مدل موجود، ترجیحاً با توان ابزار
        ("anthropic", ["claude-sonnet-4-5", "claude-3-7-sonnet-latest"]),
        ("openai", ["gpt-5", "gpt-4.1", "gpt-4o"]),
        ("openrouter", ["anthropic/claude-sonnet-4.5", "x-ai/grok-4", "deepseek/deepseek-chat-v3.1",
                        "qwen/qwen3-235b-a22b"]),
        ("gemini", ["gemini-2.5-pro", "gemini-2.5-flash"]),
        ("deepseek", ["deepseek-chat", "deepseek-reasoner"]),
        ("xai", ["grok-4", "grok-3"]),
        ("groq", ["moonshotai/kimi-k2-instruct", "llama-3.3-70b-versatile"]),
    ],
    "expert2": [
        ("cloudflare", ["@cf/meta/llama-3.3-70b-instruct-fp8-fast"]),
        ("avalai", ["gpt-5-mini", "gemini-2.5-flash", "gpt-4o-mini", "claude-3-5-haiku", "gpt-5", "claude-sonnet-4-5"]),
        ("gapgpt", ["gpt-4o-mini", "gpt-5-mini", "gpt-4o", "gpt-5", "claude-sonnet-4-5"]),
        ("metisai", ["gpt-4o-mini", "gpt-4o", "gpt-5"]),
        ("winkapi", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
        ("sinox", ["gpt-4o-mini", "gpt-5", "claude-sonnet-4-5"]),
        
        ("openrouter", ["qwen/qwen3-235b-a22b", "meta-llama/llama-3.3-70b-instruct",
                        "mistralai/mistral-large", "deepseek/deepseek-chat-v3.1"]),
        ("deepseek", ["deepseek-chat", "deepseek-reasoner"]),
        ("xai", ["grok-3", "grok-4"]),
        ("groq", ["llama-3.3-70b-versatile"]),
        ("openai", ["gpt-4o-mini", "gpt-4.1-mini"]),
        ("gemini", ["gemini-2.5-flash"]),
        ("anthropic", ["claude-3-5-haiku-latest"]),
    ],
}

# --------------------------------------------------------------- تنظیمات اجرا
@dataclass
class Settings:
    panel_size: int = 4            # چند خبره موازی جواب بدهند
    critique_rounds: int = 1       # چند دور نقد متقابل
    verify: bool = True            # بازبینی نهایی
    use_tools: bool = True         # ابزارها (کد، فایل، وب) فعال باشند
    max_tool_rounds: int = 3       # حداکثر دور ابزار برای هر خبره
    temperature_expert: float = 0.7
    temperature_judge: float = 0.25
    temperature_router: float = 0.1
    request_timeout: int = 180
    max_retries: int = 3
    stream: bool = True
    memory: bool = True            # یادگیری از نتایج قبلی
    # ── عامل خودمختار
    agent_max_steps: int = 24      # سقف گام‌های اجرا (۰ = بی‌نهایت)
    agent_auto_continue: bool = True
    # ── دستیار تلگرام
    telegram_allow_all: bool = True
    # ── اتصال از ایران
    proxy: str = ""                  # مثل http://127.0.0.1:7890 یا socks5://127.0.0.1:1080
    proxy_scope: str = "foreign"     # foreign = فقط پرووایدرهای جهانی | all = همه
    model_tier: str = "max"          # max | balanced | cheap
    auto_fallback: bool = True       # اگر پرووایدری جواب نداد، بعدی را امتحان کن
    knowledge_broadcast: bool = True  # کاوش موازی چند مدل + اشتراک یافته‌ها میان همه
    broadcast_size: int = 3           # چند مدل موازی کاوش کنند (۲ تا ۴)

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls()
        for f in s.__dataclass_fields__:  # type: ignore[attr-defined]
            raw = os.environ.get("MEGA_" + f.upper())
            if raw is None:
                continue
            cur = getattr(s, f)
            try:
                if isinstance(cur, bool):
                    setattr(s, f, raw.strip().lower() in ("1", "true", "yes", "on"))
                elif isinstance(cur, int):
                    setattr(s, f, int(raw))
                elif isinstance(cur, float):
                    setattr(s, f, float(raw))
                else:
                    setattr(s, f, raw)
            except ValueError:
                pass
        return s


def configured_providers() -> list[Provider]:
    """پرووایدرهای فعال (شامل کلید داخلی حالت نمایشی)."""
    return [p for p in PROVIDERS.values() if p.configured]


def real_configured_providers() -> list[Provider]:
    """پرووایدرهایی که کاربر **کلید واقعی** داده است (بدون کلید نمایشی)."""
    return [p for p in PROVIDERS.values() if p.real_key]


def has_real_keys() -> bool:
    return bool(real_configured_providers())


def key_status() -> dict[str, dict]:
    return {
        p.id: {
            "label": p.label,
            # «configured» = کلید واقعی کاربر (کلید داخلی حالت نمایشی شمرده نمی‌شود)
            "configured": p.configured and bool(p.real_key),
            "demo_bridge": p.configured and not p.real_key,
            "env_key": p.env_key,
            "signup": p.signup,
            "prefix": (p.real_key[:8] + "…") if p.real_key and len(p.real_key) > 8 else None,
        }
        for p in PROVIDERS.values()
    }


def has_any_key() -> bool:
    return bool(configured_providers())


def available_providers() -> list[Provider]:
    """پرووایدرهایی که الان مدل دارند (شامل مدل نمایشی داخلی)."""
    return [p for p in PROVIDERS.values() if p.key]


def has_any_model() -> bool:
    return bool(available_providers())


# ------------------------------------------------------------- ابزارهای متن
FAMILY = {
    "gpt": "OpenAI", "o1": "OpenAI", "o3": "OpenAI", "o4": "OpenAI", "chatgpt": "OpenAI",
    "claude": "Anthropic", "gemini": "Google", "gemma": "Google", "palm": "Google",
    "deepseek": "DeepSeek", "grok": "xAI", "qwen": "Alibaba", "llama": "Meta",
    "mistral": "Mistral", "mixtral": "Mistral", "kimi": "Moonshot", "phi": "Microsoft",
    "command": "Cohere", "sonar": "Perplexity", "yi": "01.AI", "glm": "Zhipu",
}


def family_of(model: str) -> str:
    m = model.lower()
    for k, v in FAMILY.items():
        if k in m:
            return v
    return "Other"


def pretty_model(model: str) -> str:
    return re.sub(r"^(.*?)/(.*)$", lambda m: f"{m.group(2)} · {m.group(1)}", model)


load_env()


def _csv(name: str) -> list[str]:
    """مقدار کاماجدا از متغیر محیطی (مثل CUSTOM_MODELS)."""
    raw = (os.environ.get(name) or "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


# مدل‌های پرووایدر سفارشی (اگر کاربر مشخص کرده باشد)
CUSTOM_MODELS: list[str] = _csv("CUSTOM_MODELS")

# ─────────── سرویس‌های رایگان (بدون کارت بانکی) ───────────
PROVIDERS["groq"] = Provider(
    "groq", "Groq — رایگان و بسیار سریع (بدون کارت)", "openai",
    "https://api.groq.com/openai/v1", "GROQ_API_KEY",
    ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3-32b", "llama-3.3-70b-versatile"],
    "https://console.groq.com/keys",
)

PROVIDERS["openrouter"] = Provider(
    "openrouter", "OpenRouter — مدل‌های رایگان (بدون کارت)", "openai",
    "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
    ["openai/gpt-oss-120b:free", "openai/gpt-oss-20b:free", "qwen/qwen3-coder:free",
     "google/gemma-3-27b-it:free", "deepseek/deepseek-r1:free"],
    "https://openrouter.ai/keys",
)

PROVIDERS["mistral"] = Provider(
    "mistral", "Mistral — حالت رایگان (بدون کارت)", "openai",
    "https://api.mistral.ai/v1", "MISTRAL_API_KEY",
    ["mistral-small-latest", "mistral-medium-latest", "codestral-latest", "mistral-large-latest"],
    "https://console.mistral.ai/api-keys",
)

PROVIDERS["cloudflare"] = Provider(
    "cloudflare", "Cloudflare Workers AI — رایگان روزانه (بدون کارت)", "openai",
    "https://api.cloudflare.com/client/v4/accounts/ACCOUNT_ID/ai/v1", "CLOUDFLARE_API_TOKEN",
    ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/qwen/qwen2.5-coder-32b-instruct",
     "@cf/google/gemma-4-26b-a4b-it", "@cf/openai/gpt-oss-120b",
     "@cf/meta/llama-3.1-8b-instruct-fp8"],
    "https://dash.cloudflare.com/profile/api-tokens",
)

# پرووایدر سفارشی: هر آدرس سازگار با OpenAI (گیت‌وی دیگر، Ollama، vLLM، LM Studio…)
PROVIDERS["custom"] = Provider(
    "custom", "سفارشی (هر آدرس سازگار با OpenAI)", "openai",
    "https://example.com/v1", "CUSTOM_API_KEY",
    CUSTOM_MODELS or ["gpt-4o", "claude-sonnet-4-5", "gemini-2.5-pro", "llama3.1", "qwen2.5"],
    "—",
)

# میزبان‌های پیش‌فرض قابل بازنویسی با .env  (مثلاً OPENAI_BASE_URL برای مدل محلی)
for _p in PROVIDERS.values():
    env_base = os.environ.get(f"{_p.id.upper()}_BASE_URL")
    if env_base:
        if _p.id == "custom":
            _p.custom_base = env_base.rstrip("/")     # گیت‌وی/مدل سفارشی
        else:
            _p.base_url = env_base.rstrip("/")

# Cloudflare: شناسه حساب از .env خوانده می‌شود
_cf_id = (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
if _cf_id:
    PROVIDERS["cloudflare"].base_url = (
        f"https://api.cloudflare.com/client/v4/accounts/{_cf_id}/ai/v1")
def apply_env_bases() -> None:
    """آدرس‌ها را دوباره از متغیرهای محیطی می‌سازد (بعد از ذخیرهٔ کلید صدا زده می‌شود)."""
    for _p in PROVIDERS.values():
        env_base = os.environ.get(f"{_p.id.upper()}_BASE_URL")
        if env_base:
            if _p.id == "custom":
                _p.custom_base = env_base.rstrip("/")
            else:
                _p.base_url = env_base.rstrip("/")
    _cid = (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    if _cid:
        PROVIDERS["cloudflare"].base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/{_cid}/ai/v1")


_providers_free = tuple(k for k in ("groq", "openrouter", "mistral", "cloudflare") if k in PROVIDERS)

SETTINGS = Settings.from_env()
