"""
MEGA-AI  |  دستیار تلگرام
================================================================
ربات تلگرام که پیام تو را به «کارگزار مطلق» می‌دهد و خروجی را برمی‌گرداند:
متن، پیام صوتی (تبدیل به متن)، عکس/سند (ذخیره و تحلیل)، دستور سریع، ارسال فایل‌های ساخته‌شده.

اجرا:
    TELEGRAM_BOT_TOKEN=123:ABC python -m mega.telegram_bot
یا از رابط وب: «دستیار تلگرام → شروع»
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from .agent import MegaAgent
from .config import SETTINGS, WORKSPACE
from .media import stt, tts
from .memory import MEMORY

API = "https://api.telegram.org"

HELP = """🧠 *MEGA-AI — کارگزار اختصاصی تو*

هر چیزی بنویس، اجرا می‌کنم: کد می‌نویسم و تست می‌کنم، پروژه می‌سازم،
ویدیو و تبلیغ می‌سازم، صداگذاری می‌کنم، داده می‌گیرم و تحلیل می‌کنم، پکیج نصب می‌کنم.

🎙 پیام صوتی بفرست → متن می‌کنم و اجرا می‌کنم.
📎 فایل/عکس بفرست → ذخیره و رویش کار می‌کنم.
🔊 با دستور `/say متن` جواب را صوتی می‌فرستم.
📊 `/status` وضعیت سیستم، `/new` نشست تازه.

مثال‌ها:
• «یک تبلیغ ۲۰ ثانیه‌ای برای یک کافه بساز»
• «یک سایت معرفی خدمات بساز و اجرا کن»
• «این داده را تحلیل کن و نمودار بده» (فایل را بفرست)"""


class TelegramBot:
    def __init__(self, token: str, allow_all: bool = True):
        self.token = token.strip()
        self.api = f"{API}/bot{self.token}"
        self.allow_all = allow_all
        self.offset = 0
        self.running = False
        self.stats = {"messages": 0, "jobs": 0, "errors": 0, "started": None}
        self.allowed: set[int] = set()
        self.sessions: dict[int, str] = {}
        self.agent = MegaAgent(SETTINGS, MEMORY)

    # ------------------------------------------------------------ API تلگرام
    async def call(self, method: str, **params) -> dict:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(f"{self.api}/{method}", json=params)
        if r.status_code >= 400:
            self.stats["errors"] += 1
            return {"ok": False, "error": r.text[:300]}
        return r.json()

    async def send(self, chat_id: int, text: str, markdown: bool = True) -> None:
        text = (text or "…").strip()
        for chunk in [text[i:i + 3800] for i in range(0, len(text), 3800)] or ["…"]:
            await self.call("sendMessage", chat_id=chat_id, text=chunk,
                            parse_mode="Markdown" if markdown else None,
                            disable_web_page_preview=True)

    async def typing(self, chat_id: int) -> None:
        await self.call("sendChatAction", chat_id=chat_id, action="typing")

    async def send_file(self, chat_id: int, path: Path, caption: str = "") -> None:
        method = {"mp4": "sendVideo", "mov": "sendVideo", "mp3": "sendAudio", "wav": "sendAudio",
                  "ogg": "sendVoice", "png": "sendPhoto", "jpg": "sendPhoto", "jpeg": "sendPhoto"}.get(
            path.suffix.lstrip(".").lower(), "sendDocument")
        field = {"sendVideo": "video", "sendAudio": "audio", "sendVoice": "voice",
                 "sendPhoto": "photo", "sendDocument": "document"}[method]
        async with httpx.AsyncClient(timeout=300) as c:
            with open(path, "rb") as f:
                r = await c.post(f"{self.api}/{method}",
                                 data={"chat_id": chat_id, "caption": caption[:900]},
                                 files={field: (path.name, f)})
        if r.status_code >= 400:
            self.stats["errors"] += 1

    async def download(self, file_id: str, dest: Path) -> Optional[Path]:
        info = await self.call("getFile", file_id=file_id)
        if not info.get("ok"):
            return None
        url = f"{API}/file/bot{self.token}/{info['result']['file_path']}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as c:
            r = await c.get(url)
        if r.status_code != 200:
            return None
        dest.write_bytes(r.content)
        return dest

    # ------------------------------------------------------------ حلقه‌ی اصلی
    async def poll_forever(self) -> None:
        self.running = True
        self.stats["started"] = time.time()
        while self.running:
            try:
                data = await self.call("getUpdates", offset=self.offset, timeout=25,
                                       allowed_updates=["message"])
                for upd in data.get("result", []) or []:
                    self.offset = upd["update_id"] + 1
                    try:
                        await self.handle(upd)
                    except Exception as e:  # noqa: BLE001
                        self.stats["errors"] += 1
                        msg = (upd.get("message") or {})
                        if msg.get("chat", {}).get("id"):
                            await self.send(msg["chat"]["id"], f"⚠️ خطا: {type(e).__name__}: {e}")
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                await asyncio.sleep(3)

    def stop(self) -> None:
        self.running = False

    # ------------------------------------------------------------ پردازش پیام
    async def handle(self, upd: dict) -> None:
        msg = upd.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        if not chat_id:
            return
        who = (msg.get("from") or {}).get("id")
        if not self.allow_all:
            if not self.allowed:
                self.allowed.add(chat_id)          # اولین کاربر = مالک
            elif chat_id not in self.allowed:
                await self.send(chat_id, "⛔️ این ربات اختصاصی است.")
                return
        self.stats["messages"] += 1

        text = (msg.get("text") or "").strip()
        session = self.sessions.setdefault(chat_id, f"tg-{chat_id}")

        # ── دستورهای سریع
        if text.startswith("/"):
            cmd, _, rest = text.partition(" ")
            rest = rest.strip()
            if cmd in ("/start", "/help"):
                await self.send(chat_id, HELP); return
            if cmd == "/status":
                from .config import configured_providers, key_status
                st = key_status()
                rows = "\n".join(f"{'✅' if v['configured'] else '—'} {v['label']}"
                                 for v in st.values())
                await self.send(chat_id, f"*وضعیت*\n{rows}\n\nآماده: "
                                         f"{'بله' if configured_providers() else 'حالت نمایشی'}\n"
                                         f"پیام‌ها: {self.stats['messages']} · کارها: {self.stats['jobs']}\n"
                                         f"نشست: `{session}`", markdown=True)
                return
            if cmd == "/new":
                self.sessions[chat_id] = f"tg-{chat_id}-{int(time.time())}"
                await self.send(chat_id, "🆕 نشست تازه شروع شد."); return
            if cmd == "/say":
                if not rest:
                    await self.send(chat_id, "مثال: `/say سلام، این یک تست صوتی است`"); return
                p = WORKSPACE / f"tg-{chat_id}" / f"say-{int(time.time())}.mp3"
                res = await tts(rest, p)
                if res.get("ok"):
                    await self.typing(chat_id)
                    await self.send_file(chat_id, p, "🔊 فایل صوتی")
                else:
                    await self.send(chat_id, f"⚠️ {res.get('error')}")
                return
            if cmd in ("/run", "/agent"):
                if not rest:
                    await self.send(chat_id, "مثال: `/run یک سایت کاری بساز`"); return
                await self.do_job(chat_id, rest, session)
                return
            await self.send(chat_id, "دستور ناشناخته. /help")
            return

        # ── پیام صوتی → متن
        voice = msg.get("voice") or msg.get("audio") or msg.get("video_note")
        if voice and not text:
            await self.typing(chat_id)
            dest = WORKSPACE / f"tg-{chat_id}" / f"voice-{int(time.time())}.ogg"
            got = await self.download(voice["file_id"], dest)
            if not got:
                await self.send(chat_id, "⚠️ دانلود پیام صوتی ناموفق بود."); return
            # تلگرام ogg می‌دهد؛ به mp3 تبدیل می‌کنیم تا موتورهای تشخیص راحت‌تر بخوانند
            mp3 = dest.with_suffix(".mp3")
            import subprocess, shutil
            if shutil.which("ffmpeg"):
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                                "-i", str(dest), str(mp3)], timeout=120)
            res = await stt(mp3 if mp3.exists() else dest)
            if not res.get("ok"):
                await self.send(chat_id, f"🎙 پیام صوتی دریافت شد ولی متن نشد: {res.get('error')}\n"
                                         f"متن را بنویس تا اجرا کنم.")
                return
            text = res["text"].strip()
            await self.send(chat_id, f"🎙 شنیدم: «{text}»")

        # ── فایل/سند/عکس → ذخیره و ارجاع به عامل
        doc = msg.get("document")
        photo = msg.get("photo")
        note = ""
        if doc or photo:
            fid = doc["file_id"] if doc else photo[-1]["file_id"]
            name = (doc or {}).get("file_name") or f"photo-{int(time.time())}.jpg"
            dest = WORKSPACE / f"tg-{chat_id}" / re.sub(r"[^\w.\-]", "_", name)
            got = await self.download(fid, dest)
            if got:
                note = f"\n\n(کاربر فایل فرستاده: `{dest.name}` — در پوشه‌ی کاری همین نشست موجود است" \
                       f"{'؛ متن/سند را بخوان و تحلیل کن' if doc else '؛ اگر ابزار بینایی نداری، از کاربر بخواه توضیح دهد'}.)"
                await self.send(chat_id, f"📎 فایل ذخیره شد: `{dest.name}`")

        if not text and not note:
            return
        await self.do_job(chat_id, text + note, session)

    # ------------------------------------------------------------ اجرای کار
    async def do_job(self, chat_id: int, goal: str, session: str) -> None:
        self.stats["jobs"] += 1
        await self.send(chat_id, "⚙️ شروع کردم؛ دارم اجرا می‌کنم…")
        await self.typing(chat_id)
        steps, tools, artifacts, final = 0, [], [], ""
        model_name = ""
        progress_id: Optional[int] = None
        last_push = 0.0
        try:
            async for ev in self.agent.run_stream(goal, session_id=session):
                t = ev["type"]
                if t == "model":
                    model_name = ev["name"]
                elif t == "plan" and ev.get("plan", {}).get("steps"):
                    plan = ev["plan"]
                    lines = [f"🗺 *نقشه‌ی اجرا* ({len(plan['steps'])} گام)"]
                    for s in plan["steps"][:8]:
                        lines.append(f"{s.get('n','•')}. {str(s.get('action',''))[:90]}")
                    await self.send(chat_id, "\n".join(lines))
                elif t == "tool":
                    steps += 1
                    tools.append(ev["name"])
                    now = time.time()
                    if now - last_push > 6:
                        last_push = now
                        await self.typing(chat_id)
                        await self.send(chat_id, f"🔧 در حال اجرا… ({len(tools)} ابزار تا حالا)\n"
                                                 f"آخرین: `{ev['name']}`", markdown=True)
                elif t == "artifact":
                    artifacts.append(ev["path"])
                elif t == "final":
                    final = ev["text"]
                elif t == "error":
                    await self.send(chat_id, f"⚠️ {ev['message']}")
            head = f"✅ *انجام شد* ({len(tools)} ابزار"
            head += f" · مدل: {model_name})" if model_name else ")"
            await self.send(chat_id, head + "\n\n" + final[:3500])
            # ارسال خودکار فایل‌های ساخته‌شده (مهم‌ترین‌ها)
            sdir = WORKSPACE / re.sub(r"[^A-Za-z0-9_-]", "_", session)
            priority = {".mp4": 3, ".png": 2, ".mp3": 2, ".jpg": 2, ".pdf": 2, ".csv": 1, ".xlsx": 1}
            files = [sdir / a for a in artifacts if (sdir / a).exists()]
            files.sort(key=lambda p: priority.get(p.suffix, 0), reverse=True)
            for p in files[:6]:
                try:
                    await self.send_file(chat_id, p, f"📦 {p.name} ({p.stat().st_size//1024} KB)")
                except Exception:  # noqa: BLE001
                    continue
        except Exception as e:  # noqa: BLE001
            self.stats["errors"] += 1
            await self.send(chat_id, f"⚠️ خطای اجرا: {type(e).__name__}: {e}")


# ---------------------------------------------------------------- اجرای مستقل
BOT: Optional[TelegramBot] = None


async def main(token: str) -> None:
    global BOT
    BOT = TelegramBot(token, allow_all=SETTINGS.telegram_allow_all)
    me = await BOT.call("getMe")
    who = (me.get("result") or {}).get("username", "?")
    print(f"🤖 ربات فعال شد: @{who}   (Ctrl+C برای توقف)")
    await BOT.poll_forever()


if __name__ == "__main__":
    tok = os.environ.get("TELEGRAM_BOT_TOKEN") or (sys.argv[1] if (sys := __import__("sys")).argv[1:] else "")
    if not tok:
        print("توکن لازم است:  TELEGRAM_BOT_TOKEN=123:ABC python -m mega.telegram_bot")
        raise SystemExit(1)
    try:
        asyncio.run(main(tok))
    except KeyboardInterrupt:
        print("\nمتوقف شد.")
