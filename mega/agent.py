"""
MehranAiShabestar  |  عامل خودمختار (Mega Agent)
================================================================
یک کارگزار که «کار» را تا آخر انجام می‌دهد، نه اینکه فقط جواب بدهد:

    خواسته‌ی تو → برنامه‌ریزی → اجرای ابزارهای واقعی → دیدن نتیجه → اصلاح → تحویل فایل

بدون سقف مصنوعی: می‌تواند پکیج نصب کند، کد بنویسد و اجرا کند، داده بگیرد، مدل بسازد،
ویدیو/تبلیغ بسازد، پروژه بسازد، تست کند، با APIها حرف بزند و خروجی را تحویل بدهد.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from .config import SETTINGS, WORKSPACE, Settings, family_of, has_any_model, pretty_model
from .media import make_ad, make_image, make_video, poster_from_photo, probe_duration, stt, tts
from .memory import MEMORY, Memory
from .providers import ChatResult, ModelSpec, chat, resolve_role
from .skills import SkillBox, update_libraries
from .tools import ToolBox, extract_tool_calls, strip_tool_blocks

AGENT_SYS = """تو «کارگزار مطلق» (Mega Agent) هستی: دستیار اختصاصی و همه‌فن‌حریف مالک این سیستم.
مأموریت: خواسته‌ی کاربر را **واقعاً اجرا کنی** و یک خروجی قابل استفاده تحویل بدهی — نه توضیح، نه وعده.

قواعد طلایی:
1. خودت تصمیم بگیر و عمل کن؛ از کاربر نپرس «آیا انجام بدهم؟» — فقط کارِ واقعی را انجام بده.
2. برای هر ادعا مدرک اجرایی بیاور: خروجی واقعی دستور، فایل ساخته‌شده، عدد اندازه‌گیری‌شده.
3. اگر خطا خوردی، خودت علت را پیدا کن و راه دیگر را امتحان کن (تا سه راه‌حل متفاوت).
4. برنامه‌ریزی کوتاه بکن، بعد سریع برو سر اجرا. گام‌ها را با ابزار پیش ببر.
5. هر فایلی که می‌سازی داخل پوشه‌ی کاری همان نشست باشد (مسیر نسبی).
6. در پایان: خلاصه‌ی کوتاه + فهرست دقیق فایل‌های تحویلی + دستور اجرای آن‌ها را بده.
7. هیچ محدودیت ساختگی از خودت درنیاور؛ اگر ابزاری لازم است، نصبش کن.
8. زبان پاسخ = زبان کاربر. کوتاه، دقیق، بدون تعارف.
9. هر کدی که می‌نویسی را **واقعاً اجرا کن** و خروجی‌اش را ببین؛ اگر خطا داد، خودت اصلاح کن و دوباره اجرا کن
   تا سبز شود. کد اجرانشده تحویل نده.
10. اگر کاربر فایل/عکس/داده فرستاده باشد، اول آن را با ابزار analyze_file (یا برای عکس، بینایی مدل)
    واقعاً تحلیل کن و در پاسخ از یافته‌های همان فایل استفاده کن — نه از حدس.
11. کارهای سنگین را موازی ببر: چند دستور مستقل را در یک گام با چند بلوک ابزار اجرا کن.
12. اگر کاربر گفت «روی گیت‌هاب بگذار / پوش کن / مخزن بساز» از ابزار github استفاده کن
    (action=push_folder یا push_project با repo؛ اگر نامی نگفت یک نام مناسب پیشنهاد بده).

13. این سیستم ویندوز است. دستورهای لینوکسی (ls, cat, sed, grep, rm, mkdir -p, touch) کار نمی‌کنند؛
    برای فایل از ابزارهای write_file / read_file / list_files و برای اجرا از python یا دستورهای ویندوزی استفاده کن.
14. ساختن فایل فقط با ابزار write_file انجام می‌شود — نه با shell و نه با echo و نه با > :
    ```tool
    {"name": "write_file", "args": {"path": "index.html", "content": "<html>…</html>"}}
    ```
15. پیش از finish، با read_file یا list_files مطمئن شو فایل‌ها **واقعاً** ساخته شده‌اند. هرگز ادعای ساختِ
    فایلی که وجود ندارد نکن. اگر ابزاری خطا داد، همان دستور را تکرار نکن؛ راه دیگری را امتحان کن.

سبک کار: مثل یک مهندس ارشد + کارگردان + تحلیل‌گر که هم‌زمان کار می‌کند.
"""


AGENT_SPECS: list[dict] = [
    {"name": "finish", "args": {"answer": "string"},
     "desc": "پایان کار و تحویل پاسخ نهایی همراه فهرست فایل‌های ساخته‌شده"},
    {"name": "tts", "args": {"text": "string", "path": "string", "voice": "string"},
     "desc": "تبدیل متن به گفتار فارسی/انگلیسی (edge-tts) و ذخیره‌ی mp3"},
    {"name": "stt", "args": {"path": "string"}, "desc": "تبدیل فایل صوتی به متن"},
    {"name": "make_image", "args": {"path": "string", "title": "string", "subtitle": "string",
                                    "lines": "list[str]", "theme": "string", "ratio": "9:16|16:9|1:1"},
     "desc": "ساخت تصویر/پوستر/اسلاید با گرادیان و متن فارسی"},
    {"name": "make_video", "args": {"scenes": "list[{title,text,lines,image,seconds,theme}]",
                                    "path": "string", "ratio": "string", "voice": "string",
                                    "subtitles": "bool", "music": "bool", "brand": "string"},
     "desc": "ساخت ویدیو با گویندگی، زیرنویس سوخته و حرکت نرم (ffmpeg)"},
    {"name": "make_ad", "args": {"topic": "string", "path": "string", "ratio": "string",
                                 "voice": "string", "brand": "string", "music": "bool",
                                 "image": "string (عکس خودِ کاربر برای پس‌زمینه)"},
     "desc": "ساخت تبلیغ ویدیویی آماده (قلاب→مشکل→راه‌حل→اثبات→فراخوان)؛ با image از عکس خودِ کاربر استفاده می‌کند"},
    {"name": "poster_from_photo", "args": {"photo": "string (مسیر عکس)", "path": "string",
                                           "title": "string", "subtitle": "string",
                                           "lines": "list[str]", "badge": "string",
                                           "footer": "string", "caption": "string",
                                           "ratio": "9:16|16:9|1:1", "theme": "string"},
     "desc": "از عکس خودِ کاربر پوستر واقعی می‌سازد (برش هوشمند + پرده‌ی تیره + متن فارسی)"},
    {"name": "analyze_file", "args": {"path": "string (مسیر فایل)", "question": "string"},
     "desc": "تحلیل واقعی فایل کاربر: تصویر/داده/کد/متن/سند/آرشیو/صدا/ویدیو + نمودار + گزارش فارسی"},
    {"name": "github", "args": {"action": "whoami|list_repos|push_folder|push_session|push_project|"
                                          "read_file|write_file|create_issue|list_issues",
                                "repo": "string (name یа owner/name)", "folder": "string (مسیر پوشه)",
                                "path": "string (مسیر فایل داخل مخزن)", "content": "string",
                                "message": "string", "private": "bool", "branch": "string"},
     "desc": "اتصال واقعی به گیت‌هاب با کلید کاربر: ساخت مخزن، فرستادن پوشه/پروژه در یک کامیت، "
             "خواندن/نوشتن فایل، issue — برای وقتی می‌گوید «این را روی گیت‌هابم بگذار»"},
    {"name": "update_libraries", "args": {},
     "desc": "به‌روزرسانی کتابخانه‌ها و گزارش پکیج‌های قدیمی"},
    {"name": "use_council", "args": {"question": "string"},
     "desc": "مشورت سریع با دو مدل دیگر روی یک سؤال فنی"},
]


def _manual(boxes_specs: list[dict]) -> str:
    lines = ["", "## ابزارهای تو", "هر بار برای استفاده از ابزار، دقیقاً این قالب را در پاسخ بنویس:",
             "```tool", '{"name": "نام_ابزار", "args": {…}}', "```",
             "می‌توانی چند بلوک پشت‌سرهم بدهی. نتیجه‌ی هر ابزار بلافاصله به تو برمی‌گردد.",
             "برای پایان کار و تحویل، ابزار finish را صدا بزن.", ""]
    for t in boxes_specs:
        args = ", ".join(f"{k}: {v}" for k, v in t["args"].items()) or "—"
        lines.append(f"- `{t['name']}({args})` → {t['desc']}")
    return "\n".join(lines)


PLANNER_SYS = """تو برنامه‌ریز ارشد اجرا هستی. برای رسیدن به هدف کاربر، یک نقشه‌ی اجرایی JSON بده:
{"goal": "…", "steps": [{"n": 1, "action": "…", "tool": "نام ابزار", "output": "خروجی مورد انتظار"}, …],
 "deliverables": ["فایل/نتیجه‌ی نهایی"], "risks": ["…"]}
فقط JSON. گام‌ها عملی و پشت‌سرهم باشند (بین ۳ تا ۸ گام)."""


class MegaAgent:
    """عامل خودمختار با دسترسی کامل به ابزارهای سیستم."""

    def __init__(self, settings: Optional[Settings] = None, memory: Optional[Memory] = None):
        self.s = settings or SETTINGS
        self.m = memory or MEMORY

    # ------------------------------------------------------------------ اجرا
    async def run_stream(self, goal: str, session_id: str = "agent", mode: str = "agent",
                         history: Optional[list[dict]] = None) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(self._run(goal, session_id, mode, q, history or []))
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=0.2)
                yield ev
                continue
            except asyncio.TimeoutError:
                pass
            if task.done() and q.empty():
                break
        try:
            await task
        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": f"{type(e).__name__}: {e}"}

    # ------------------------------------------------------------- درون‌کار
    async def _run(self, goal: str, session_id: str, mode: str,
                   q: asyncio.Queue, history: list[dict]) -> None:
        t0 = time.time()
        sdir = WORKSPACE / re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "agent")
        sdir.mkdir(parents=True, exist_ok=True)
        box = SkillBox(sdir)
        await q.put({"type": "meta", "session": session_id, "goal": goal, "dir": str(sdir.name),
                     "models_available": has_any_model(), "mode": mode})

        model = await resolve_role("agent" if mode == "agent" else "judge", 0.35, 4096)
        if not model:
            model = await resolve_role("expert", 0.35, 4096)
        if not model:
            await q.put({"type": "error", "message": "هیچ مدلی در دسترس نیست (کلید API ثبت نشده)."})
            await q.put({"type": "final", "text": "برای اجرای کارگزار، حداقل یک کلید API لازم است."})
            return
        await q.put({"type": "model", "name": model.name, "provider": model.provider})

        # ۱) برنامه‌ریزی
        steps: list[dict] = []
        planner = await resolve_role("router", 0.2, 1200)
        if planner:
            await q.put({"type": "phase", "id": "plan", "title": "برنامه‌ریزی", "state": "start",
                         "model": planner.name})
            r = await chat(planner, [{"role": "system", "content": PLANNER_SYS},
                                     {"role": "user", "content": goal[:4000]}], self.s)
            plan = self._json(r.text) if r.ok else {}
            steps = plan.get("steps") or []
            await q.put({"type": "plan", "plan": plan or {"goal": goal, "steps": []}})
            await q.put({"type": "phase", "id": "plan", "state": "done",
                         "seconds": r.seconds, "text": json.dumps(plan, ensure_ascii=False, indent=2)})
        # ۲) اجرای گام‌ها
        run_id = self.m.start_run(session_id, goal, "agent", mode,
                                  {"plan": steps, "kind": "agent"})
        max_steps = self.s.agent_max_steps if self.s.agent_max_steps > 0 else 10_000
        uploads = self._uploads_note(sdir)          # فایل‌هایی که کاربر آپلود کرده
        msgs = [
            {"role": "system", "content": AGENT_SYS + _manual(box.specs() + AGENT_SPECS) +
                                          (f"\n\n## نقشه‌ی پیشنهادی برنامه‌ریز\n"
                                           f"{json.dumps(steps, ensure_ascii=False)}" if steps else "") +
                                          (f"\n\n{uploads}" if uploads else "")},
            {"role": "user", "content": self._context(goal, history)},
        ]
        if goal.lower().strip().startswith(("سلام", "hi", "hello")) and len(goal) < 40:
            msgs[1]["content"] = goal + "\n\n(کاربر فقط احوال‌پرسی کرده؛ کوتاه جواب بده و بگو چه کارهایی می‌توانی انجام دهی.)"

        final_text, artifacts, step_no, files_seen = "", [], 0, 0
        repeats: dict[str, int] = {}      # نگهبان تکرار: جلوی حلقه‌ی بی‌فایده را می‌گیرد
        for step in range(max_steps):
            step_no = step + 1
            await q.put({"type": "step", "n": step_no, "state": "start"})
            r: ChatResult = await chat(model, msgs, self.s,
                                       lambda t: q.put_nowait({"type": "delta", "n": step_no, "text": t}))
            self.m.add_stage(run_id, "agent", r.model or model.model, r.provider or model.provider,
                             r.text, r.seconds, r.ok, r.tokens)
            if not r.ok:
                await q.put({"type": "step", "n": step_no, "state": "failed", "error": r.error})
                break
            calls = extract_tool_calls(r.text, allowed=self._allowed_names(box))
            visible = strip_tool_blocks(r.text)
            await q.put({"type": "thought", "n": step_no, "text": visible})
            if not calls:
                if visible.strip() and len(visible.strip()) > 120 and (artifacts or step > 6):
                    final_text = visible.strip()      # پاسخ کامل بدون ابزار
                    await q.put({"type": "step", "n": step_no, "state": "done", "text": visible})
                    break
                msgs.append({"role": "assistant", "content": r.text})
                msgs.append({"role": "user", "content": "ادامه بده و کار را با ابزارها پیش ببر؛ "
                                                        "اگر تمام شد با ابزار finish خروجی نهایی را بده."})
                await q.put({"type": "step", "n": step_no, "state": "done", "text": visible})
                continue

            msgs.append({"role": "assistant", "content": r.text})
            results, finished, repeated = [], None, False
            for c in calls[:4]:
                name, args = c["name"], c.get("args") or {}
                sig = f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)[:200]}"
                repeats[sig] = repeats.get(sig, 0) + 1
                if repeats[sig] >= 3 and name != "finish":
                    repeated = True
                    results.append(f"[{name} قبلاً همین آرگومان‌ها را سه بار اجرا کردی؛ نتیجه‌ی تازه‌ای "
                                   f"ندارد. گام بعدی را برو یا اگر کار تمام است finish بزن.]")
                    continue
                await q.put({"type": "tool", "n": step_no, "name": name,
                             "args": {k: (str(v)[:400] if not isinstance(v, (int, float, bool)) else v)
                                      for k, v in (args or {}).items()}})
                res = await self._dispatch(box, name, args, session_id)
                await q.put({"type": "tool_result", "n": step_no, "name": name, "result": res[:4000]})
                results.append(f"[نتیجه‌ی {name}]\n{res}")
                if name == "finish":
                    finished = str(res).replace("__FINISH__", "", 1).strip() or visible.strip()
            # فایل‌های تازه‌ساخته‌شده را اعلام کن
            for p in self._new_files(sdir):
                if p not in artifacts:
                    artifacts.append(p)
                    _rel = str(p.relative_to(sdir))
                    await q.put({"type": "artifact", "path": _rel, "name": p.name,
                                 "size": p.stat().st_size, "kind": self._kind(p),
                                 "url": f"/files/{sdir.name}/{_rel}"})
            files_seen = len(artifacts)
            if finished is not None:
                final_text = finished
                await q.put({"type": "step", "n": step_no, "state": "done", "text": "✅ کار تمام شد"})
                break
            nudge = ("⚠️ همین کار را قبلاً انجام داده‌ای؛ آن را تکرار نکن. الان یا یک گام واقعاً جدید بردار، "
                     "یا اگر کار تمام است با ابزار finish پاسخ نهایی + فهرست فایل‌ها را بده."
                     if repeated else
                     "گام بعدی را اجرا کن. اگر کار تمام شده، با ابزار finish پاسخ نهایی و فهرست "
                     "فایل‌ها را بده.")
            msgs.append({"role": "user", "content": "نتیجه‌ی ابزارها:\n\n" + "\n\n".join(results) +
                                                    f"\n\n{nudge}"})
            await q.put({"type": "step", "n": step_no, "state": "done",
                         "text": f"{len(calls)} ابزار اجرا شد"})
        else:
            final_text = final_text or "به سقف گام‌های اجرا رسیدم؛ خروجی‌های ساخته‌شده در فهرست فایل‌ها است."

        # ۳) جمع‌بندی تحویل
        if not final_text:
            final_text = "کار اجرا شد. فایل‌های تولیدشده در فهرست پایین موجود است."
        final_text = final_text.replace("__FINISH__", "").strip()
        summary = self._deliverables(artifacts, sdir)
        if summary and "/files/" not in final_text:
            final_text += "\n\n" + summary
        if not final_text.strip():
            final_text = "کار اجرا شد." + ("\n" + summary if summary else "")
        self.m.finish_run(run_id, final_text, {"steps": step_no, "seconds": round(time.time() - t0, 1),
                                               "artifacts": [str(a.relative_to(sdir)) for a in artifacts]})
        await q.put({"type": "final", "text": final_text, "steps": step_no,
                     "seconds": round(time.time() - t0, 1), "model": model.name,
                     "artifacts": [{"path": str(p.relative_to(sdir)), "name": p.name,
                                    "size": p.stat().st_size, "kind": self._kind(p),
                                    "url": f"/files/{sdir.name}/{p.relative_to(sdir)}"}
                                   for p in artifacts],
                     "dir": str(sdir.name), "run_id": run_id})

    # ------------------------------------------------------------ گیت‌هاب
    async def _github(self, args: dict, box: SkillBox) -> str:
        from .github_tool import GitHub, GitHubError, test_token, api_base
        action = str(args.get("action") or "whoami").strip().lower()
        repo = str(args.get("repo") or "").strip()
        if action in ("test", "whoami", "me"):
            r = await test_token()
            if not r.get("ok"):
                return (f"اتصال گیت‌هاب برقرار نشد: {r.get('error')}\nراهنما: {r.get('hint')}"
                        "\n(کلید را در پنل → ⚙️ تنظیمات → گیت‌هاب بگذار)")
            return (f"✅ متصل به گیت‌هاب به‌عنوان «{r['login']}»"
                    f"{' (' + r['name'] + ')' if r.get('name') else ''}\n"
                    f"دسترسی‌ها: {r.get('scopes')}\nمی‌توانم مخزن بسازم و کد بفرستم.")
        try:
            gh = GitHub()
        except GitHubError as e:
            return f"کلید گیت‌هاب تنظیم نشده: {e}"
        try:
            if action in ("list_repos", "repos"):
                items = await gh.list_repos(limit=int(args.get("limit") or 30))
                if not items:
                    return "هیچ مخزنی پیدا نشد."
                return json.dumps(items, ensure_ascii=False, indent=1)
            if action in ("create_repo", "create"):
                info = await gh.create_repo(repo or str(args.get("name") or ""),
                                            private=bool(args.get("private", True)),
                                            description=str(args.get("description") or ""))
                return f"مخزن ساخته شد: {info['full_name']} → {info['url']} (خصوصی: {info['private']})"
            if action in ("push_project", "push_self"):
                res = await gh.push_project(message=str(args.get("message") or "MEGA-AI: انتشار پروژه"),
                                           repo=repo, private=bool(args.get("private", True)),
                                           branch=str(args.get("branch") or ""))
                return json.dumps(res, ensure_ascii=False)
            if action in ("push_session", "push_workspace"):
                sess = str(args.get("folder") or args.get("session") or box.dir.name)
                res = await gh.push_session(sess, repo,
                                            message=str(args.get("message") or "MEGA-AI: خروجی نشست"),
                                            private=bool(args.get("private", True)))
                return json.dumps(res, ensure_ascii=False)
            if action in ("push_folder", "push"):
                folder = str(args.get("folder") or args.get("path") or box.dir)
                fp = self._resolve_folder(folder, box)
                res = await gh.push_folder(fp, repo,
                                           message=str(args.get("message") or "MEGA-AI: انتشار پوشه"),
                                           private=bool(args.get("private", True)),
                                           branch=str(args.get("branch") or ""),
                                           description=str(args.get("description") or ""))
                return json.dumps(res, ensure_ascii=False)
            if action in ("read_file", "get_file"):
                got = await gh.get_file(repo, str(args.get("path") or ""),
                                        ref=str(args.get("branch") or ""))
                if not got.get("exists"):
                    return f"فایل «{args.get('path')}» در {repo} پیدا نشد."
                if got.get("type") == "dir":
                    return json.dumps(got.get("items"), ensure_ascii=False)
                return got.get("content", "")[:6000]
            if action in ("write_file", "put_file"):
                r = await gh.put_file(repo, str(args.get("path") or ""),
                                      str(args.get("content") or ""),
                                      str(args.get("message") or "MEGA-AI: بروزرسانی فایل"),
                                      branch=str(args.get("branch") or ""))
                return json.dumps(r, ensure_ascii=False)
            if action in ("create_issue", "issue"):
                r = await gh.create_issue(repo, str(args.get("title") or args.get("message") or "بدون عنوان"),
                                          str(args.get("body") or args.get("content") or ""))
                return f"issue ساخته شد: #{r['number']} → {r['url']}"
            if action in ("list_issues", "issues"):
                return json.dumps(await gh.list_issues(repo, limit=int(args.get("limit") or 20)),
                                  ensure_ascii=False)
            return f"عملیات ناشناخته: {action} (API گیت‌هاب: {api_base()})"
        except GitHubError as e:
            return f"خطای گیت‌هاب: {e}"
        except Exception as e:  # noqa: BLE001
            return f"خطای غیرمنتظره در گیت‌هاب: {type(e).__name__}: {e}"

    def _resolve_folder(self, raw: str, box: SkillBox) -> str:
        """مسیر یک پوشه را پیدا می‌کند: مطلق، نسبی، یا داخل پوشه‌ی کاری."""
        cands = [Path(raw), box.dir / raw, WORKSPACE / raw, WORKSPACE / box.dir.name / raw]
        for c in cands:
            try:
                if c.is_dir():
                    return str(c.resolve())
            except Exception:
                continue
        return str(box.dir)

    # ------------------------------------------------------------ مسیرها
    def _resolve(self, raw: str, box: SkillBox) -> Optional[Path]:
        """مسیر فایل کاربر را پیدا می‌کند: مطلق، نسبی، فقط نام فایل، یا داخل پوشه‌ی نشست."""
        raw = (raw or "").strip().strip('"\'` ')
        if not raw:
            return None
        cands = [Path(raw)]
        if not Path(raw).is_absolute():
            cands = [box.dir / raw, WORKSPACE / raw, WORKSPACE / box.dir.name / "uploads" / raw]
            cands.append(WORKSPACE / box.dir.name / Path(raw).name)
        for c in cands:
            try:
                if c.is_file():
                    return c.resolve()
            except Exception:
                continue
        # جست‌وجوی نام فایل داخل نشست و پوشه‌ی آپلود
        name = Path(raw).name
        for root in (box.dir, WORKSPACE):
            try:
                for hit in root.rglob(name):
                    if hit.is_file():
                        return hit.resolve()
            except Exception:
                continue
        return None

    def _uploads_note(self, sdir: Path) -> str:
        """فهرست فایل‌های آپلودی/موجود کاربر تا مدل بداند چه چیزی در اختیار دارد."""
        groups = [sdir / "uploads", sdir]
        seen: list[Path] = []
        for g in groups:
            if not g.is_dir():
                continue
            for f in sorted(g.iterdir(), key=lambda x: -x.stat().st_mtime if x.is_file() else 0):
                if f.is_file() and f not in seen and not f.name.startswith("."):
                    seen.append(f)
                if len(seen) >= 25:
                    break
        if not seen:
            return ""
        from .analyze import kind_of
        lines = ["## فایل‌های آپلودی کاربر (همین‌ها در اختیار توست)",
                 "برای تحلیل هرکدام: analyze_file(path=…) — برای پوسترسازی از عکس: poster_from_photo(photo=…)"]
        for f in seen[:25]:
            try:
                lines.append(f"- `{f}` ({kind_of(f)} · {f.stat().st_size / 1024:.0f}KB)")
            except Exception:
                continue
        return "\n".join(lines)

    # ------------------------------------------------------------ ابزارها
    async def _dispatch(self, box: SkillBox, name: str, args: dict, session_id: str) -> str:
        """ابزارهای اختصاصی عامل + بقیه در SkillBox."""
        args = {k: v for k, v in (args or {}).items() if isinstance(k, str)}
        try:
            if name == "finish":
                ans = str(args.get("answer") or args.get("text") or args.get("result") or "").strip()
                return "__FINISH__" + ans
            if name == "tts":
                r = await tts(str(args.get("text", "")), box.dir / str(args.get("path", "voice.mp3")),
                              voice=str(args.get("voice") or "fa-IR-DilaraNeural"))
                return json.dumps(r, ensure_ascii=False)
            if name == "stt":
                r = await stt(box.dir / str(args.get("path", "")))
                return json.dumps(r, ensure_ascii=False)
            if name == "make_image":
                bg = str(args.get("bg") or args.get("image") or "").strip()
                bg_path = self._resolve(bg, box) if bg else None
                p = make_image(box.dir / str(args.get("path", "image.png")),
                               str(args.get("title", "")), args.get("lines"),
                               theme=str(args.get("theme") or "بنفش شب"),
                               ratio=str(args.get("ratio") or "9:16"),
                               subtitle=str(args.get("subtitle", "")),
                               footer=str(args.get("footer", "")),
                               caption=str(args.get("caption") or ""),
                               badge=str(args.get("badge") or ""),
                               bg=bg_path)
                return f"تصویر ساخته شد: {Path(p).name}" + (f" (پس‌زمینه: {Path(bg_path).name})" if bg_path else "")
            if name == "poster_from_photo":
                ph = self._resolve(str(args.get("photo") or args.get("image") or ""), box)
                if not ph or not Path(ph).is_file():
                    return ("عکس ورودی پیدا نشد. مسیر را از فهرست «فایل‌های آپلودی کاربر» بردار.")
                r = poster_from_photo(ph, box.dir / str(args.get("path", "poster.png")),
                                      title=str(args.get("title") or ""), lines=args.get("lines"),
                                      subtitle=str(args.get("subtitle") or ""),
                                      badge=str(args.get("badge") or ""),
                                      footer=str(args.get("footer") or ""),
                                      caption=str(args.get("caption") or ""),
                                      ratio=str(args.get("ratio") or "9:16"),
                                      theme=str(args.get("theme") or "بنفش شب"))
                return json.dumps(r, ensure_ascii=False)
            if name == "github":
                return await self._github(args, box)
            if name == "analyze_file":
                fp = self._resolve(str(args.get("path") or ""), box)
                if not fp or not Path(fp).is_file():
                    return "فایل پیدا نشد؛ مسیر را از فهرست فایل‌های آپلودی کاربر بردار."
                from .analyze import analyze_file as _an
                r = await _an(fp, question=str(args.get("question") or ""),
                              out_dir=box.dir / "analysis", settings=self.s, use_model=True)
                if not r.get("ok"):
                    return f"تحلیل ناموفق: {r.get('error')}"
                extra = ("\n\n[نمودارها: " + "، ".join(Path(c).name for c in r.get("charts", [])) + "]"
                         if r.get("charts") else "")
                return r["report"] + extra
            if name == "make_video":
                scenes = args.get("scenes") or []
                if isinstance(scenes, str):
                    scenes = json.loads(scenes)
                r = await make_video(scenes, box.dir / str(args.get("path", "video.mp4")),
                                     ratio=str(args.get("ratio") or "9:16"),
                                     theme=str(args.get("theme") or "بنفش شب"),
                                     voice=str(args.get("voice") or "fa-IR-DilaraNeural"),
                                     subtitles=bool(args.get("subtitles", True)),
                                     music=bool(args.get("music", False)),
                                     brand=str(args.get("brand", "")),
                                     motion=bool(args.get("motion", True)))
                return json.dumps(r, ensure_ascii=False)
            if name == "make_ad":
                _img = str(args.get("image") or args.get("photo") or "").strip()
                _img_path = self._resolve(_img, box) if _img else None
                r = await make_ad(str(args.get("topic", "")), box.dir / str(args.get("path", "ad.mp4")),
                                  ratio=str(args.get("ratio") or "9:16"),
                                  voice=str(args.get("voice") or "fa-IR-FaridNeural"),
                                  brand=str(args.get("brand", "")),
                                  music=bool(args.get("music", True)),
                                  image=_img_path)
                return json.dumps(r, ensure_ascii=False)
            if name == "update_libraries":
                return await update_libraries()
            if name == "use_council":
                # چند مدل دیگر را هم روی همین مسئله می‌گیرد (مشورت سریع)
                question = str(args.get("question", ""))
                specs = []
                for off in range(3):
                    sp = await resolve_role("expert", 0.6, 1600, offset=off)
                    if sp and sp.id != f"x":
                        specs.append(sp)
                outs = await asyncio.gather(*[
                    chat(sp, [{"role": "system", "content": "پاسخ کوتاه، فنی و صریح بده."},
                              {"role": "user", "content": question[:3000]}], self.s) for sp in specs])
                return "\n\n".join(f"### {sp.name}\n{r.text[:1200]}" for sp, r in zip(specs, outs) if r.ok) \
                       or "[مدل دیگری در دسترس نبود]"
            return await box.run(name, args)
        except Exception as e:  # noqa: BLE001
            return f"[خطای اجرای {name}: {type(e).__name__}: {e}]"

    @staticmethod
    def _allowed_names(box: SkillBox) -> set[str]:
        from .tools import TOOL_SPECS
        names = {t["name"] for t in TOOL_SPECS} | {t["name"] for t in AGENT_SPECS}
        names |= {t["name"] for t in box.specs()}
        return names

    # ------------------------------------------------------------ کمکی‌ها
    @staticmethod
    def _json(text: str) -> dict:
        for blob in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", re.S):
            try:
                return json.loads(blob)
            except Exception:
                pass
        m = re.search(r"\{.*\}", text or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
        return {}

    @staticmethod
    def _new_files(sdir: Path) -> list[Path]:
        """فایل‌های قابل تحویل (فایل‌های موقت و پوشه‌های کاری را نادیده می‌گیرد)."""
        out = []
        for p in sorted(sdir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(sdir)
            if any(part.startswith(("_", "scene", "clip")) or part.endswith("_parts")
                   for part in rel.parts) or p.suffix in (".pyc", ".log", ".part"):
                continue
            out.append(p)
        return out

    @staticmethod
    def _kind(p: Path) -> str:
        ext = p.suffix.lower()
        for kind, exts in (("video", (".mp4", ".webm", ".mkv", ".mov")),
                           ("audio", (".mp3", ".wav", ".m4a", ".ogg")),
                           ("image", (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")),
                           ("data", (".csv", ".xlsx", ".xls", ".json", ".db", ".sqlite")),
                           ("doc", (".md", ".txt", ".pdf", ".docx")),
                           ("web", (".html", ".css", ".js", ".ts", ".jsx", ".vue")),
                           ("code", (".py", ".sh", ".dart", ".java", ".kt", ".rs", ".go", ".sql")),
                           ("archive", (".zip", ".tar", ".gz", ".7z"))):
            if ext in exts:
                return kind
        return "file"

    def _deliverables(self, artifacts: list[Path], sdir: Path) -> str:
        if not artifacts:
            return ""
        lines = ["", "### 📦 فایل‌های تحویلی"]
        for p in artifacts[:25]:
            try:
                size = p.stat().st_size
                lines.append(f"- `{p.relative_to(sdir)}` — {size/1024:.0f} KB "
                             f"({self._kind(p)}) · لینک: `/files/{sdir.name}/{p.relative_to(sdir)}`")
            except Exception:
                continue
        return "\n".join(lines)

    def _context(self, goal: str, history: list[dict]) -> str:
        if not history:
            return goal
        parts = ["## گفت‌وگوی قبلی همین نشست"]
        for h in history[-3:]:
            parts.append(f"کاربر: {(h.get('prompt') or '')[:300]}\nسیستم: {(h.get('final') or '')[:400]}")
        parts.append("\n## خواسته‌ی فعلی\n" + goal)
        return "\n\n".join(parts)
