"""
MEGA-AI  |  مهارت‌ها و ابزارهای توسعه
================================================================
توانایی‌های اجرایی سطح‌سیستم: نصب پکیج، به‌روزرسانی کتابخانه‌ها، git، HTTP،
دانلود، ffmpeg، اجرای پس‌زمینه و اسکافولد پروژه (API، سایت، PWA، ربات، موبایل…).
هر «مهارت» یک پوشه/ماژول پایتون در skills/ است که خودکار بارگذاری می‌شود.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from .config import WORKSPACE, ROOT

SKILLS_DIR = ROOT / "skills"
SKILLS_DIR.mkdir(exist_ok=True)
MAX_OUT = 8000
BLOCKED = re.compile(r"(rm\s+-rf\s+/(?!home|tmp)|mkfs|>\s*/dev/sd|:\s*\(\)\s*\{)", re.I)


# --------------------------------------------------------------- اسکافولدها
def _tpl_fastapi(name: str) -> dict[str, str]:
    return {
        "main.py": f'''"""API پروژه‌ی {name} — با uvicorn اجرا کن: uvicorn main:app --reload"""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="{name}")


class Item(BaseModel):
    title: str
    done: bool = False


DB: list[Item] = []


@app.get("/health")
def health():
    return {{"ok": True, "items": len(DB)}}


@app.get("/items")
def list_items():
    return DB


@app.post("/items")
def add_item(item: Item):
    DB.append(item)
    return item
''',
        "requirements.txt": "fastapi\nuvicorn[standard]\n",
        "README.md": f"# {name}\n\n```bash\npip install -r requirements.txt\nuvicorn main:app --reload\n```\n",
    }


def _tpl_html_site(name: str) -> dict[str, str]:
    return {
        "index.html": f'''<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title>
<style>
 body{{margin:0;font-family:Vazirmatn,Tahoma,sans-serif;background:#0b1020;color:#eaeefb}}
 .wrap{{max-width:900px;margin:auto;padding:48px 20px}}
 h1{{font-size:42px;margin:0 0 12px}}
 .btn{{display:inline-block;background:linear-gradient(135deg,#7c5cff,#22d3ee);color:#fff;
       padding:12px 22px;border-radius:12px;text-decoration:none;font-weight:700}}
 .card{{background:#151d38;border:1px solid #27325c;border-radius:16px;padding:20px;margin:16px 0}}
</style></head><body><div class="wrap">
<h1>{name}</h1>
<p>سایت آماده است — این متن را عوض کن.</p>
<a class="btn" href="#">شروع</a>
<div class="card">بخش معرفی خدمات</div>
<div class="card">بخش نمونه‌کارها</div>
</div></body></html>
''',
        "style.css": "/* استایل‌های اختصاصی */\n",
        "app.js": "console.log('ready');\n",
    }


def _tpl_pwa(name: str) -> dict[str, str]:
    files = _tpl_html_site(name)
    files["manifest.webmanifest"] = json.dumps({
        "name": name, "short_name": name[:12], "start_url": ".", "display": "standalone",
        "background_color": "#0b1020", "theme_color": "#7c5cff",
        "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}]},
        ensure_ascii=False, indent=2)
    files["service-worker.js"] = """const C='v1';
self.addEventListener('install',e=>{self.skipWaiting()});
self.addEventListener('fetch',e=>{e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)))});
"""
    files["index.html"] = files["index.html"].replace(
        "</head>", '<link rel="manifest" href="manifest.webmanifest">\n'
                   '<link rel="apple-touch-icon" href="icon-192.png"></head>')
    return files


def _tpl_telegram_bot(name: str) -> dict[str, str]:
    return {
        "bot.py": '''"""ربات تلگرام — توکن را در متغیر محیطی BOT_TOKEN بگذار."""
import os
import httpx

TOKEN = os.environ["BOT_TOKEN"]
API = f"https://api.telegram.org/bot{TOKEN}"


def reply(chat_id: int, text: str) -> None:
    httpx.post(f"{API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=30)


def main() -> None:
    offset = 0
    print("bot running…")
    while True:
        r = httpx.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=60).json()
        for u in r.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            if "text" in msg:
                reply(msg["chat"]["id"], f"دریافت شد: {msg['text']}")


if __name__ == "__main__":
    main()
''',
        "requirements.txt": "httpx\n",
        "README.md": f"# {name}\n\n```bash\nexport BOT_TOKEN=123:abc\npython bot.py\n```\n",
    }


def _tpl_scraper(name: str) -> dict[str, str]:
    return {
        "scrape.py": '''"""نمونه‌ی استخراج داده + ذخیره در CSV/JSON."""
import csv
import json
import re
from pathlib import Path

import httpx

URL = "https://example.com"


def fetch(url: str = URL) -> str:
    r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.text


def parse(html: str) -> list[dict]:
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    rows = [{"title": (title.group(1).strip() if title else ""), "url": URL}]
    return rows


def save(rows: list[dict], stem: str = "data") -> None:
    Path(f"{stem}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(f"{stem}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    data = parse(fetch())
    save(data)
    print(f"{len(data)} ردیف ذخیره شد.")
''',
        "requirements.txt": "httpx\n",
    }


def _tpl_data_analysis(name: str) -> dict[str, str]:
    return {
        "analyze.py": '''"""تحلیل داده + نمودار.  ورودی: فایل CSV/Excel"""
import sys
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(path: str) -> pd.DataFrame:
    p = Path(path)
    df = pd.read_excel(p) if p.suffix in (".xlsx", ".xls") else pd.read_csv(p)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def main(path: str, out: str = "report") -> None:
    df = load(path)
    print("ابعاد:", df.shape)
    print(df.describe(include="all").to_string()[:2000])
    num = df.select_dtypes("number")
    if len(num.columns):
        num.plot(figsize=(10, 5))
        plt.tight_layout()
        plt.savefig(f"{out}.png", dpi=140)
        print(f"نمودار ذخیره شد: {out}.png")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data.csv")
''',
        "requirements.txt": "pandas\nmatplotlib\nopenpyxl\n",
    }


def _tpl_flutter(name: str) -> dict[str, str]:
    slug = re.sub(r"[^a-z0-9_]", "_", name.lower()) or "my_app"
    return {
        "pubspec.yaml": f"""name: {slug}
description: {name}
publish_to: 'none'
version: 1.0.0+1
environment:
  sdk: ">=3.3.0 <4.0.0"
dependencies:
  flutter:
    sdk: flutter
  http: ^1.2.0
dev_dependencies:
  flutter_test:
    sdk: flutter
flutter:
  uses-material-design: true
""",
        "lib/main.dart": f'''import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() => runApp(const App());

class App extends StatelessWidget {{
  const App({{super.key}});
  @override
  Widget build(BuildContext context) => MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: ThemeData(colorSchemeSeed: const Color(0xFF7C5CFF), useMaterial3: true),
        home: const Home(),
      );
}}

class Home extends StatefulWidget {{
  const Home({{super.key}});
  @override
  State<Home> createState() => _HomeState();
}}

class _HomeState extends State<Home> {{
  String status = 'آماده';
  Future<void> ping() async {{
    setState(() => status = 'در حال بررسی…');
    try {{
      final r = await http.get(Uri.parse('https://example.com'));
      setState(() => status = 'پاسخ سرور: ${{r.statusCode}}');
    }} catch (e) {{
      setState(() => status = 'خطا: $e');
    }}
  }}

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('{name}')),
        body: Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Text(status),
            const SizedBox(height: 16),
            FilledButton(onPressed: ping, child: const Text('تست اتصال')),
          ]),
        ),
      );
}}
''',
        "README.md": f"""# {name} (Flutter)

```bash
flutter create .          # اگر پروژه را از صفر می‌سازی
flutter pub get
flutter run               # روی گوشی/شبیه‌ساز
flutter build apk --release   # خروجی اندروید (نیاز به Android SDK)
```
""",
    }


def _tpl_chrome_extension(name: str) -> dict[str, str]:
    return {
        "manifest.json": json.dumps({
            "manifest_version": 3, "name": name, "version": "1.0",
            "description": name, "action": {"default_popup": "popup.html"},
            "permissions": ["activeTab", "scripting"]}, ensure_ascii=False, indent=2),
        "popup.html": f'<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">'
                      f'<body style="width:280px;font-family:Tahoma"><h3>{name}</h3>'
                      f'<button id="go">اجرا</button><pre id="out"></pre>'
                      f'<script src="popup.js"></script></body></html>',
        "popup.js": '''document.getElementById('go').onclick = async () => {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  chrome.scripting.executeScript({target: {tabId: tab.id},
    func: () => document.title}).then(r =>
    document.getElementById('out').textContent = 'عنوان: ' + JSON.stringify(r));
};
''',
    }


TEMPLATES = {
    "fastapi": ("API پایتون (FastAPI)", _tpl_fastapi),
    "site": ("سایت HTML/CSS/JS", _tpl_html_site),
    "pwa": ("وب‌اپ نصب‌شدنی / اپ موبایل PWA", _tpl_pwa),
    "telegram-bot": ("ربات تلگرام", _tpl_telegram_bot),
    "scraper": ("استخراج داده از وب", _tpl_scraper),
    "data-analysis": ("تحلیل داده و نمودار", _tpl_data_analysis),
    "flutter": ("اپ موبایل فلاتر", _tpl_flutter),
    "extension": ("افزونه‌ی کروم", _tpl_chrome_extension),
}


# ------------------------------------------------------------------ جعبه‌ابزار
class SkillBox:
    """ابزارهای سطح‌سیستم: پکیج، git، HTTP، ffmpeg، اجرا، اسکافولد، مهارت‌ها."""

    def __init__(self, session_dir: Path):
        self.dir = Path(session_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.artifacts: list[str] = []

    # ------------------------------------------------------------ مشخصات ابزارها
    @staticmethod
    def specs() -> list[dict[str, Any]]:
        return [
            {"name": "shell", "args": {"command": "string", "timeout": "int (ثانیه، پیش‌فرض ۱۲۰)"},
             "desc": "اجرای هر دستور شل در پوشه‌ی کاری (نصب، ساخت، تست، اجرا)"},
            {"name": "python", "args": {"code": "string"},
             "desc": "اجرای کد پایتون و گرفتن خروجی واقعی"},
            {"name": "pip", "args": {"packages": "string", "upgrade": "bool"},
             "desc": "نصب/به‌روزرسانی پکیج‌های پایتون (مثلاً 'pandas openpyxl')"},
            {"name": "npm", "args": {"command": "string"},
             "desc": "دستور npm/npx در پروژه (install, run build, …)"},
            {"name": "git", "args": {"args": "string"},
             "desc": "دستور git (init, add, commit, clone, …)"},
            {"name": "http", "args": {"method": "string", "url": "string",
                                      "json": "object", "data": "object", "headers": "object"},
             "desc": "درخواست HTTP به هر API (GET/POST/PUT/DELETE) و دریافت پاسخ"},
            {"name": "download", "args": {"url": "string", "path": "string"},
             "desc": "دانلود فایل از اینترنت"},
            {"name": "ffmpeg", "args": {"args": "string"},
             "desc": "اجرای ffmpeg برای پردازش ویدیو/صدا/تصویر"},
            {"name": "run_bg", "args": {"command": "string", "name": "string"},
             "desc": "اجرای یک سرویس در پس‌زمینه و برگرداندن لاگ آن"},
            {"name": "scaffold", "args": {"kind": "string", "path": "string", "name": "string"},
             "desc": "ساخت اسکلت پروژه: " + " | ".join(TEMPLATES)},
            {"name": "install_skill", "args": {"source": "string", "name": "string"},
             "desc": "نصب مهارت جدید: نام پکیج pip، آدرس فایل .py یا مخزن git"},
            {"name": "list_skills", "args": {}, "desc": "فهرست مهارت‌های نصب‌شده"},
            {"name": "write_file", "args": {"path": "string", "content": "string"},
             "desc": "ساخت/بازنویسی فایل"},
            {"name": "read_file", "args": {"path": "string"}, "desc": "خواندن فایل"},
            {"name": "list_files", "args": {"path": "string"}, "desc": "لیست فایل‌ها"},
            {"name": "web_search", "args": {"query": "string"}, "desc": "جست‌وجوی وب"},
            {"name": "fetch_url", "args": {"url": "string"}, "desc": "خواندن متن صفحه‌ی وب"},
        ]

    # ------------------------------------------------------------------ اجرا
    async def run(self, name: str, args: dict) -> str:
        fn = getattr(self, f"_t_{name}", None)
        if fn is None:
            return f"[ابزار ناشناخته: {name}]"
        clean = {k: v for k, v in (args or {}).items() if isinstance(k, str)}
        try:
            out = await fn(**clean)
        except TypeError as e:
            return f"[آرگومان نامعتبر برای {name}: {e}]"
        except Exception as e:  # noqa: BLE001
            return f"[خطای {name}: {type(e).__name__}: {e}]"
        out = str(out)
        return out[:MAX_OUT] + ("\n…(بریده شد)" if len(out) > MAX_OUT else "")

    def _safe(self, path: str) -> Path:
        p = (self.dir / (path or ".")).resolve()
        if not str(p).startswith(str(self.dir.resolve())):
            raise ValueError(f"مسیر بیرون از پوشه‌ی کاری: {path}")
        return p

    async def _exec(self, argv, cwd: Optional[Path] = None, timeout: int = 120,
                    shell: bool = False) -> str:
        if shell and BLOCKED.search(" ".join(argv)):
            return "[دستور به دلایل امنیتی مجاز نیست]"
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=str(cwd or self.dir), stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1",
                     "PIP_DISABLE_PIP_VERSION_CHECK": "1", "DEBIAN_FRONTEND": "noninteractive",
                     "npm_config_yes": "true"}) if not shell else \
                await asyncio.create_subprocess_shell(
                    " ".join(argv), cwd=str(cwd or self.dir), stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                         "DEBIAN_FRONTEND": "noninteractive", "npm_config_yes": "true"})
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=max(5, int(timeout)))
        except asyncio.TimeoutError:
            return f"[اجرا بیش از {timeout} ثانیه طول کشید و متوقف شد]"
        text = out.decode("utf-8", "replace").strip()
        return (text or "(بدون خروجی)") + f"\n[کد خروج: {proc.returncode}]"

    # ---------------------------------------------------------------- ابزارها
    async def _t_shell(self, command: str = "", timeout: int = 120, **_) -> str:
        cmd = (command or "").strip()
        # «echo متن > فایل» در ویندوز با کوتیشن و < > خطا می‌دهد → خودمان فایل را می‌سازیم
        m = re.match(r"^echo\s+(?P<text>.+?)\s*>>?\s*(?P<path>[^\s>|]+)\s*$", cmd, re.S)
        if m:
            text = m.group("text").strip().strip("'\"").replace("\\n", "\n")
            try:
                target = self._safe(m.group("path").strip().strip("'\""))
                target.parent.mkdir(parents=True, exist_ok=True)
                prev = target.read_text(encoding="utf-8", errors="replace") if (">>" in cmd and target.exists()) else ""
                target.write_text(prev + text + "\n", encoding="utf-8")
                return f"فایل ساخته شد: {target.relative_to(self.dir)} ({len(text)} کاراکتر)\n[کد خروج: 0]"
            except Exception as e:  # noqa: BLE001
                return f"[خطا در نوشتن فایل: {type(e).__name__}: {e}]"
        if os.name == "nt" and re.search(r"[<>]", cmd):
            return ("[این دستور روی ویندوز اجرا نمی‌شود. برای ساختن فایل از ابزار write_file "
                    "استفاده کن (args: path و content) و برای خواندن از read_file.]")
        return await self._exec([cmd], timeout=int(timeout or 120), shell=True)

    async def _t_python(self, code: str = "", **_) -> str:
        f = self.dir / f"_run_{int(time.time()*1000) % 10**9}.py"
        f.write_text(code or "", encoding="utf-8")
        return await self._exec([sys.executable, str(f)], timeout=180)

    async def _t_pip(self, packages: str = "", upgrade: bool = False, **_) -> str:
        pkgs = [p for p in re.split(r"[\s,]+", packages or "") if p]
        if not pkgs:
            return await self._exec([sys.executable, "-m", "pip", "list", "--outdated"], timeout=180)
        argv = [sys.executable, "-m", "pip", "install", "-q", "--no-input"]
        if upgrade:
            argv.append("--upgrade")
        out = await self._exec(argv + pkgs, timeout=600)
        ok = "[کد خروج: 0]" in out
        if ok:   # پکیج‌های نصب‌شده را به‌عنوان «مهارت» ثبت کن تا در فهرست بمانند
            ledger = SKILLS_DIR / "installed-pip.txt"
            old = ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []
            stamp = time.strftime("%Y-%m-%d %H:%M")
            for pkg in pkgs:
                if pkg.startswith("-"):
                    continue
                ver = ""
                try:
                    import importlib.metadata as md
                    ver = md.version(pkg)
                except Exception:
                    ver = ""
                old.append(f"{pkg}{'==' + ver if ver else ''}  ({stamp})")
            ledger.write_text("\n".join(dict.fromkeys(old)), encoding="utf-8")
            out = f"✅ نصب/به‌روزرسانی شد: {', '.join(p for p in pkgs if not p.startswith('-'))}\n" + out
        return out

    async def _t_npm(self, command: str = "", **_) -> str:
        return await self._exec(["npm"] + (command.split() or ["--version"]), timeout=600)

    async def _t_git(self, args: str = "", **_) -> str:
        return await self._exec(["git"] + args.split(), timeout=180)

    async def _t_http(self, method: str = "GET", url: str = "", json: Any = None,
                      data: Any = None, headers: Any = None, **_) -> str:
        if not url:
            return "[url لازم است]"
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            r = await c.request(method.upper(), url, json=json,
                                data=data if not json else None,
                                headers={**(headers or {}), "User-Agent": "MEGA-AI/1.0"}
                                if isinstance(headers, dict) else {"User-Agent": "MEGA-AI/1.0"})
        body = r.text
        try:
            body = json.dumps(r.json(), ensure_ascii=False, indent=2)
        except Exception:
            pass
        return f"HTTP {r.status_code}\n{body[:6000]}"

    async def _t_download(self, url: str = "", path: str = "", **_) -> str:
        if not url:
            return "[url لازم است]"
        target = self._safe(path or os.path.basename(url.split("?")[0]) or "download.bin")
        target.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as c:
            async with c.stream("GET", url) as r:
                r.raise_for_status()
                with open(target, "wb") as f:
                    async for chunk in r.aiter_bytes(1 << 16):
                        f.write(chunk)
        self.artifacts.append(str(target))
        return f"دانلود شد: {target.relative_to(self.dir)} ({target.stat().st_size / 1024:.0f} KB)"

    async def _t_ffmpeg(self, args: str = "", **_) -> str:
        if not shutil.which("ffmpeg"):
            return "[ffmpeg نصب نیست]"
        return await self._exec(["ffmpeg", "-hide_banner", "-y"] + args.split(), timeout=900)

    async def _t_run_bg(self, command: str = "", name: str = "service", **_) -> str:
        log = self.dir / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', name)}.log"
        proc = await asyncio.create_subprocess_shell(
            command, cwd=str(self.dir), stdout=open(log, "wb"), stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        await asyncio.sleep(2.5)
        tail = log.read_text(errors="replace")[-1500:] if log.exists() else ""
        alive = proc.returncode is None
        return (f"سرویس «{name}» {'در حال اجراست' if alive else 'متوقف شد'} (pid={proc.pid})\n"
                f"لاگ: {log.name}\n{tail}")

    async def _t_scaffold(self, kind: str = "site", path: str = "", name: str = "پروژه", **_) -> str:
        key = (kind or "site").strip().lower()
        if key not in TEMPLATES:
            return f"[نوع نامعتبر. گزینه‌ها: {', '.join(TEMPLATES)}]"
        label, builder = TEMPLATES[key]
        target = self._safe(path or key)
        target.mkdir(parents=True, exist_ok=True)
        files = builder(name)
        for rel, content in files.items():
            f = target / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content, encoding="utf-8")
        self.artifacts.extend(str(target / r) for r in files)
        return (f"✅ {label} ساخته شد در «{target.relative_to(self.dir)}»\nفایل‌ها: "
                + ", ".join(files) + f"\n\nگام بعدی: {self._next_step(key, target.relative_to(self.dir))}")

    @staticmethod
    def _next_step(kind: str, rel: Path) -> str:
        return {
            "fastapi": f"`cd {rel} && pip install -r requirements.txt && uvicorn main:app --port 8080`",
            "site": f"`cd {rel} && python -m http.server 8080` (یا باز کردن index.html)",
            "pwa": f"`cd {rel} && python -m http.server 8080` — با Capacitor می‌شود APK ساخت",
            "telegram-bot": f"`cd {rel} && BOT_TOKEN=... python bot.py`",
            "scraper": f"`cd {rel} && pip install -r requirements.txt && python scrape.py`",
            "data-analysis": f"`cd {rel} && pip install -r requirements.txt && python analyze.py data.csv`",
            "flutter": f"`cd {rel} && flutter pub get && flutter run`",
            "extension": "در کروم: chrome://extensions → Developer mode → Load unpacked",
        }.get(kind, "اجرا و تست کن")

    # ---------------------------------------------------------------- مهارت‌ها
    async def _t_install_skill(self, source: str = "", name: str = "", **_) -> str:
        if not source:
            return "[source لازم است: نام پکیج pip یا آدرس .py یا مخزن git]"
        if re.match(r"^https?://.*\.py$", source):
            fname = (name or os.path.basename(source)).rstrip(".py") + ".py"
            target = SKILLS_DIR / fname
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
                r = await c.get(source)
            if r.status_code != 200:
                return f"[دانلود مهارت ناموفق: HTTP {r.status_code}]"
            target.write_text(r.text, encoding="utf-8")
            return f"✅ مهارت «{fname}» نصب شد (skills/{fname})"
        if re.match(r"^https?://", source):
            dest = SKILLS_DIR / (name or source.rstrip("/").split("/")[-1].removesuffix(".git"))
            out = await self._exec(["git", "clone", "--depth", "1", source, str(dest)], timeout=300)
            return f"نصب از مخزن:\n{out}"
        return await self._t_pip(packages=source)

    async def _t_list_skills(self, **_) -> str:
        rows = []
        ledger = SKILLS_DIR / "installed-pip.txt"
        if ledger.exists():
            for line in ledger.read_text(encoding="utf-8").splitlines()[-12:]:
                rows.append(f"📦 {line}")
        for p in sorted(SKILLS_DIR.iterdir()):
            desc = ""
            if p.is_file() and p.suffix == ".py":
                head = p.read_text(errors="replace")[:600]
                m = re.search(r'"""(.+?)"""', head, re.S)
                desc = (m.group(1).strip().splitlines()[0] if m else "")
            rows.append(f"{'📁' if p.is_dir() else '🐍'} {p.name}  {desc}")
        return "\n".join(rows) or "هنوز مهارتی نصب نشده (skills/ خالی است)."

    # --------------------------------------------- ابزارهای مشترک با ToolBox
    async def _t_web_search(self, query: str = "", **_) -> str:
        from .tools import ToolBox
        return await ToolBox(self.dir).run("web_search", {"query": query})

    async def _t_fetch_url(self, url: str = "", **_) -> str:
        from .tools import ToolBox
        return await ToolBox(self.dir).run("fetch_url", {"url": url})

    async def _t_write_file(self, path: str = "", content: str = "", **_) -> str:
        p = self._safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        self.artifacts.append(str(p))
        return f"نوشته شد: {p.relative_to(self.dir)} ({len(content)} کاراکتر)"

    async def _t_read_file(self, path: str = "", **_) -> str:
        p = self._safe(path)
        return p.read_text(encoding="utf-8", errors="replace")[:6000] if p.exists() else f"[نبود: {path}]"

    async def _t_list_files(self, path: str = ".", **_) -> str:
        p = self._safe(path)
        if not p.exists():
            return f"[نبود: {path}]"
        out = []
        for i in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name)):
            if i.name.startswith("_run_"):
                continue
            size = f"{i.stat().st_size/1024:.0f}KB" if i.is_file() else "dir"
            out.append(f"{'📁' if i.is_dir() else '📄'} {i.name} ({size})")
        return "\n".join(out[:100]) or "(خالی)"


def installed_skills() -> list[dict]:
    out = []
    for p in sorted(SKILLS_DIR.iterdir()) if SKILLS_DIR.exists() else []:
        out.append({"name": p.name, "dir": p.is_dir(),
                    "size": p.stat().st_size if p.is_file() else None})
    return out


async def update_libraries() -> str:
    """به‌روزرسانی کتابخانه‌های پروژه و فهرست پکیج‌های قدیمی."""
    box = SkillBox(WORKSPACE / "_system")
    req = ROOT / "requirements.txt"
    if req.exists():
        await box.run("pip", {"packages": "", "upgrade": True})
        out = await box.run("pip", {"packages": "-r " + str(req), "upgrade": True})
        outdated = await box.run("pip", {"packages": ""})
        return f"به‌روزرسانی requirements.txt:\n{out}\n\nپکیج‌های دارای نسخه‌ی جدید:\n{outdated}"
    return await box.run("pip", {"packages": ""})
