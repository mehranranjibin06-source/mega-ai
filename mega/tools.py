"""
MEGA-AI  |  جعبه‌ابزار اجرایی
------------------------------------------------
ابزارهایی که مدل‌ها می‌توانند صدا بزنند: جست‌وجوی وب، خواندن صفحه، اجرای پایتون،
شل، نوشتن/خواندن فایل. همه چیز داخل پوشه‌ی امن هر نشست محدود می‌شود.
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import re
import shlex
import sys
import unicodedata
from pathlib import Path
from typing import Any

import httpx

MAX_OUTPUT = 6000
TOOL_TIMEOUT = 40

TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "web_search", "args": {"query": "string"},
     "desc": "جست‌وجوی وب و برگرداندن عنوان+لینک+خلاصه‌ی نتایج"},
    {"name": "fetch_url", "args": {"url": "string"},
     "desc": "خواندن محتوای متنی یک صفحه‌ی وب"},
    {"name": "python", "args": {"code": "string"},
     "desc": "اجرای کد پایتون و برگرداندن خروجی واقعی (برای محاسبه، تحلیل، آزمون)"},
    {"name": "shell", "args": {"command": "string"},
     "desc": "اجرای دستور شل در پوشه‌ی کاری پروژه"},
    {"name": "write_file", "args": {"path": "string", "content": "string"},
     "desc": "ساخت/بازنویسی فایل (مسیر نسبی)"},
    {"name": "read_file", "args": {"path": "string"},
     "desc": "خواندن یک فایل"},
    {"name": "list_files", "args": {"path": "string"},
     "desc": "لیست فایل‌های یک پوشه"},
    {"name": "finish", "args": {"answer": "string"},
     "desc": "پایان کار و تحویل پاسخ نهایی"},
]

_BLOCKED = re.compile(
    r"(rm\s+-rf\s+/|mkfs|:\(\)\s*\{|dd\s+if=|shutdown|reboot|chmod\s+-R\s+777\s+/"
    r"|curl\s+.*\|\s*(ba)?sh|wget\s+.*\|\s*(ba)?sh|>\s*/dev/sd|sudo\s+rm)", re.I)


def tool_manual() -> str:
    lines = ["## ابزارهای تو", "برای استفاده از ابزار، دقیقاً این قالب را در پاسخ بنویس:",
             "```tool", '{"name": "نام_ابزار", "args": {...}}', "```",
             "بعد از هر فراخوانی ابزار، نتیجه‌اش به تو برگردانده می‌شود؛ سپس ادامه بده.",
             "وقتی نتیجه گرفتی با ابزار finish پاسخ نهایی را بده.", ""]
    for t in TOOL_SPECS:
        args = ", ".join(f"{k}: {v}" for k, v in t["args"].items())
        lines.append(f"- `{t['name']}({args})` → {t['desc']}")
    return "\n".join(lines)


def extract_tool_calls(text: str, allowed: Optional[set[str]] = None) -> list[dict]:
    """
    همه‌ی فراخوانی‌های ابزار را از متن مدل بیرون می‌کشد.
    allowed=None یعنی هر نام ابزارِ معتبر (snake_case) پذیرفته می‌شود؛
    اگر مجموعه‌ای بدهی، فقط همان‌ها قبول می‌شوند.
    """
    calls: list[dict] = []
    for m in re.finditer(r"```(?:tool|json|tool_call)?\s*(\{.*?\})\s*```", text, re.S):
        obj = _try_json(m.group(1))
        if obj:
            calls.append(obj)
    if not calls:  # بدون بلوک کد هم شاید نوشته باشد
        for m in re.finditer(r'\{\s*"name"\s*:\s*"[a-z_]+"\s*,\s*"args"\s*:\s*\{.*?\}\s*\}', text, re.S):
            obj = _try_json(m.group(0))
            if obj:
                calls.append(obj)
    out = []
    for c in calls:
        name = (c.get("name") or c.get("tool") or c.get("call") or "").strip()
        args = c.get("args") or c.get("arguments") or c.get("params") or {}
        if isinstance(args, str):
            args = _try_json(args) or {}
        if not isinstance(args, dict):
            continue
        ok = (name in allowed) if allowed else bool(re.fullmatch(r"[a-z][a-z0-9_]{1,40}", name))
        if ok:
            out.append({"name": name, "args": args})
    return out


def strip_tool_blocks(text: str) -> str:
    """بلوک‌های فراخوانی ابزار (```tool …```) را حذف می‌کند تا کاربر JSON خام نبیند.

    بلوک‌های کد معمولی (```python …) دست‌نخورده می‌مانند.
    """
    t = text or ""
    if "```" not in t:
        return t.strip()
    parts = t.split("```")
    keep: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            keep.append(part)
            continue
        head, _, body = part.partition("\n")
        tag = head.strip().lower()
        if tag in ("tool", "tool_call") or (tag == "json" and body.lstrip().startswith('{"name"')):
            continue                      # بلوک ابزار → حذف
        keep.append("```" + part + "```")
    return "".join(keep).strip()


class ToolFenceFilter:
    """متنِ در حال پخش مدل را فیلتر می‌کند: داخل بلوک ```tool هرگز به کاربر نشان داده نمی‌شود.

    خروجی: بقیهٔ متن (توضیح، کد معمولی، پاسخ نهایی) همان‌طور پخش می‌شود.
    """

    def __init__(self, emit):
        self.emit = emit
        self.buf = ""
        self.skip = False

    def feed(self, chunk: str) -> None:
        if not chunk:
            return
        self.buf += chunk
        for _ in range(200):
            if self.skip:
                i = self.buf.find("```")
                if i < 0:
                    if len(self.buf) > 4:
                        self.buf = self.buf[-4:]
                    return
                self.buf = self.buf[i + 3:]
                self.skip = False
                continue
            i = self.buf.find("```")
            if i < 0:
                if len(self.buf) > 4:
                    self.emit(self.buf[:-4])
                    self.buf = self.buf[-4:]
                return
            head, rest = self.buf[:i], self.buf[i + 3:]
            if "\n" not in rest:
                if head:
                    self.emit(head)
                self.buf = "```" + rest
                return
            first, body = rest.split("\n", 1)
            tag = first.strip().lower()
            if tag in ("tool", "tool_call") or (tag == "json" and body.lstrip().startswith('{"name"')):
                if head:
                    self.emit(head)
                self.buf = body
                self.skip = True
                continue
            self.emit(head + "```" + first + "\n")
            self.buf = body

    def flush(self) -> None:
        if self.buf and not self.skip:
            self.emit(self.buf)
        self.buf = ""


def _try_json(s: str) -> dict | None:
    try:
        o = json.loads(s)
        return o if isinstance(o, dict) else None
    except Exception:
        return None


# ------------------------------------------------------------------ اجرای ابزار
class ToolBox:
    def __init__(self, session_dir: Path, allow_net: bool = True):
        self.dir = Path(session_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.allow_net = allow_net

    def _safe(self, path: str) -> Path:
        p = (self.dir / (path or ".")).resolve()
        if not str(p).startswith(str(self.dir.resolve())):
            raise ValueError(f"دسترسی به بیرون پوشه ممنوع است: {path}")
        return p

    async def run(self, name: str, args: dict) -> str:
        try:
            fn = getattr(self, f"_t_{name}")
        except AttributeError:
            return f"[ابزار ناشناخته: {name}]"
        try:
            out = await fn(**{k: v for k, v in args.items() if isinstance(k, str)})
        except TypeError as e:
            return f"[آرگومان‌های ابزار نامعتبر: {e}]"
        except Exception as e:  # noqa: BLE001
            return f"[خطای ابزار {name}: {type(e).__name__}: {e}]"
        out = str(out)
        return out[:MAX_OUTPUT] + ("\n…(بریده شد)" if len(out) > MAX_OUTPUT else "")

    # ---------------------------------------------------------------- وب
    async def _t_web_search(self, query: str = "", **_) -> str:
        if not self.allow_net:
            return "[جست‌وجوی وب در این حالت غیرفعال است]"
        key = os.environ.get("TAVILY_API_KEY")
        if key:
            return await self._tavily(query, key)
        key = os.environ.get("BRAVE_API_KEY")
        if key:
            return await self._brave(query, key)
        key = os.environ.get("SERPER_API_KEY")
        if key:
            return await self._serper(query, key)
        return await self._ddg(query)

    async def _tavily(self, query: str, key: str) -> str:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post("https://api.tavily.com/search", json={
                "api_key": key, "query": query, "max_results": 6,
                "include_answer": True, "search_depth": "advanced"})
            d = r.json()
        parts = []
        if d.get("answer"):
            parts.append(f"خلاصه: {d['answer']}")
        for it in d.get("results", [])[:6]:
            parts.append(f"- {it.get('title')} ({it.get('url')})\n  {it.get('content','')[:400]}")
        return "\n".join(parts) or "نتیجه‌ای یافت نشد."

    async def _brave(self, query: str, key: str) -> str:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get("https://api.search.brave.com/res/v1/web/search",
                            params={"q": query, "count": 6},
                            headers={"X-Subscription-Token": key, "Accept": "application/json"})
            d = r.json()
        return "\n".join(
            f"- {w.get('title')} ({w.get('url')})\n  {w.get('description','')}"
            for w in d.get("web", {}).get("results", [])[:6]) or "نتیجه‌ای یافت نشد."

    async def _serper(self, query: str, key: str) -> str:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post("https://google.serper.dev/search", json={"q": query, "num": 6},
                             headers={"X-API-KEY": key, "content-type": "application/json"})
            d = r.json()
        out = [f"- {i.get('title')} ({i.get('link')})\n  {i.get('snippet','')}"
               for i in d.get("organic", [])[:6]]
        if d.get("answerBox", {}).get("answer"):
            out.insert(0, f"پاسخ مستقیم: {d['answerBox']['answer']}")
        return "\n".join(out) or "نتیجه‌ای یافت نشد."

    async def _ddg(self, query: str) -> str:
        """جست‌وجوی رایگان بدون کلید (DuckDuckGo lite)."""
        try:
            async with httpx.AsyncClient(timeout=25, follow_redirects=True) as c:
                r = await c.post("https://lite.duckduckgo.com/lite/", data={"q": query},
                                 headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
            if r.status_code != 200:
                return f"[جست‌وجو ناموفق: HTTP {r.status_code}]"
            rows = re.findall(r'<a rel="nofollow" href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S)
            snips = re.findall(r'class="result-snippet">(.*?)</td>', r.text, re.S)
            out = []
            for i, (url, title) in enumerate(rows[:6]):
                t = html.unescape(re.sub("<[^>]+>", "", title)).strip()
                s = html.unescape(re.sub("<[^>]+>", "", snips[i])).strip() if i < len(snips) else ""
                out.append(f"- {t}\n  {url}\n  {s[:300]}")
            return "\n".join(out) or "نتیجه‌ای یافت نشد."
        except Exception as e:  # noqa: BLE001
            return f"[جست‌وجو ناموفق: {e}]"

    async def _t_fetch_url(self, url: str = "", **_) -> str:
        if not self.allow_net:
            return "[خواندن وب غیرفعال است]"
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        async with httpx.AsyncClient(timeout=35, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
        text = r.text
        text = re.sub(r"(?is)<(script|style|nav|footer|header|svg)[^>]*>.*?</\1>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = html.unescape(re.sub(r"\s+", " ", text)).strip()
        return text[:5000] or "[صفحه محتوای متنی نداشت]"

    # ---------------------------------------------------------------- کد
    async def _t_python(self, code: str = "", **_) -> str:
        f = self.dir / f"_run_{abs(hash(code)) % 10**8}.py"
        f.write_text(code, encoding="utf-8")
        return await self._exec([sys.executable, str(f)], cwd=self.dir)

    async def _t_shell(self, command: str = "", **_) -> str:
        if _BLOCKED.search(command or ""):
            return "[دستور به دلایل امنیتی مجاز نیست]"
        return await self._exec(["/bin/bash", "-lc", command], cwd=self.dir)

    async def _exec(self, argv: list[str], cwd: Path) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=str(cwd), stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
            out, err = await asyncio.wait_for(proc.communicate(), timeout=TOOL_TIMEOUT)
        except asyncio.TimeoutError:
            return f"[اجرا بیش از {TOOL_TIMEOUT} ثانیه طول کشید و متوقف شد]"
        o = out.decode("utf-8", "replace").strip()
        e = err.decode("utf-8", "replace").strip()
        res = []
        if o:
            res.append("خروجی:\n" + o)
        if e:
            res.append("خطا:\n" + e)
        res.append(f"کد خروج: {proc.returncode}")
        return "\n".join(res)

    # ---------------------------------------------------------------- فایل
    async def _t_write_file(self, path: str = "", content: str = "", **_) -> str:
        p = self._safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"نوشته شد: {p.relative_to(self.dir)} ({len(content)} کاراکتر)"

    async def _t_read_file(self, path: str = "", **_) -> str:
        p = self._safe(path)
        if not p.exists():
            return f"[فایل پیدا نشد: {path}]"
        return p.read_text(encoding="utf-8", errors="replace")[:5000]

    async def _t_list_files(self, path: str = ".", **_) -> str:
        p = self._safe(path)
        if not p.exists():
            return f"[مسیر وجود ندارد: {path}]"
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        return "\n".join(f"{'📁' if i.is_dir() else '📄'} {i.name}" for i in items[:80]) or "(خالی)"

    async def _t_finish(self, answer: str = "", **_) -> str:
        return "__FINISH__" + answer


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return re.sub(r"\s+", " ", s).strip()
