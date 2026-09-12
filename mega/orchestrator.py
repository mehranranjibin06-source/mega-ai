"""
MEGA-AI  |  ارکستراتور چند-هوشی
================================================================
خط تولید کامل برای هر پرامپت:

  ۱) مغز راهبر (Router)      → نوع کار، سختی، طرح اجرا، معیار موفقیت
  ۲) پژوهشگر (Scout)         → اگر لازم بود، جست‌وجوی وب و خلاصه‌ی منابع
  ۳) پنل خبرگان (Experts)    → چند مدل از خانواده‌های مختلف، موازی، هرکدام با ابزار
  ۴) نقد متقابل (Critics)    → پاسخ‌های بی‌نام همدیگر را نقد و امتیازدهی می‌کنند
  ۵) داور و سنتز (Judge)     → بهترین‌ها را ادغام و تناقض‌ها را حل می‌کند
  ۶) بازبین (Verifier)       → پاسخ نهایی را با درخواست تطبیق می‌دهد، اگر ایراد بود اصلاح می‌کند
  ۷) حافظه و یادگیری         → امتیازها ذخیره می‌شود تا اجرای بعدی هوشمندانه‌تر شود
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import textwrap
import time
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from .config import (SETTINGS, WORKSPACE, Settings, available_providers, configured_providers,
                     family_of, has_any_model, pretty_model)
from .memory import MEMORY, Memory
from .providers import ChatResult, ModelSpec, chat, resolve_role
from .tools import ToolBox, extract_tool_calls, strip_tool_blocks, tool_manual

# ------------------------------------------------------------------ پرامپت‌ها

ROUTER_SYS = """تو «مغز راهبر» یک سیستم چند-هوشی هستی. کارت این است که درخواست کاربر را تحلیل کنی و
بهترین نقشه‌ی اجرا را بچینی. خروجی را فقط و فقط یک JSON بده، بدون هیچ توضیح اضافه.

کلیدها:
- task_type: یکی از "code" | "research" | "analysis" | "writing" | "math" | "translation" | "planning" | "creative" | "general"
- difficulty: عدد ۱ تا ۵
- needs_web: true اگر به اطلاعات تازه/واقعی نیاز است
- needs_tools: true اگر باید کد اجرا شود یا فایل ساخته/خوانده شود
- language: زبان پاسخ کاربر مثل "fa" یا "en"
- plan: آرایه‌ای از ۳ تا ۶ گام اجرایی مشخص
- success_criteria: آرایه‌ای از معیارهایی که پاسخ نهایی باید برآورده کند
- expert_lenses: آرایه‌ای از ۲ تا ۵ «زاویه‌ی تخصصی» که هر خبره باید از آن زاویه وارد شود
  (مثل "مهندس نرم‌افزار", "منتقد و یابنده‌ی خطا", "کارشناس داده", "طراح تجربه‌کاربری")
"""

EXPERT_SYS = """تو یکی از خبرگان یک «پنل چند-هوشی» هستی. چند مدل مختلف مستقل از هم روی این درخواست
کار می‌کنند، سپس پاسخ‌ها توسط داوران نقد و با هم ادغام می‌شوند. پس وظیفه‌ی تو حداکثر کیفیت در زاویه‌ی
تخصصی خودت است، نه گفتن حرف کلی.

قواعد:
- دقیق، مستند و بدون کلی‌گویی بنویس. عدد، مثال و گام عملی بده.
- اگر ابزار واقعی لازم داری، از آن‌ها استفاده کن و بر پایه‌ی «خروجی واقعی» نتیجه بگیر نه حدس.
- فرض‌هایت را صریح بگو و اگر چیزی نامعلوم است همان را بگو.
- پاسخ را به زبان کاربر بنویس و با markdown ساختار بده.
"""

CRITIC_SYS = """تو «نقدگر» پنل هستی. چند پاسخ بی‌نام (A، B، C، …) به یک درخواست داده شده است.
کارت: پیدا کردن خطاها، ادعاهای بی‌مدرک، نقاط قوی، و رتبه‌بندی. تعارف ممنوع؛ اگر پاسخی غلط است صریح بگو.
خروجی را با ساختار زیر بده:

## نقد هر پاسخ
### پاسخ A
- خطا/ریسک: …
- نقطه‌ی قوی: …
- آنچه از قلم افتاده: …
(برای بقیه‌ی پاسخ‌ها هم همین‌طور)

## تناقض‌ها
فهرست جاهایی که پاسخ‌ها با هم اختلاف دارند و کدام درست‌تر است و چرا.

## امتیاز
آخر پاسخ، یک بلوک json بده:
```json
{"scores": {"A": 7.5, "B": 6, "C": 8}, "verdict": "کوتاه"}
```
امتیازها از ۰ تا ۱۰ و بر پایه‌ی درستی، کامل بودن و عملی بودن.
"""

JUDGE_SYS = """تو «داور نهایی» یک پنل چند-هوشی هستی. به تو داده می‌شود: درخواست کاربر، معیارهای موفقیت،
پاسخ‌های چند مدل (با نامشان) و نقدهای صورت‌گرفته.

کارت: نوشتن **یکپارچه‌ترین و درست‌ترین پاسخ نهایی** به زبان کاربر.
- بهترین بخش‌های هر پاسخ را بردار، خطاهای شناسایی‌شده را تکرار نکن، تناقض‌ها را با استدلال حل کن.
- اگر نقدها اطلاعات تازه‌ای داشتند، در پاسخ نهایی لحاظ کن.
- ساختار روشن با markdown، بدون اشاره به «مدل A گفت/مدل B گفت» در متن اصلی.
- اگر بخشی از بهبودها را از یک یا چند مدل گرفتی، در انتها در یک بخش کوتاه «## سهم مدل‌ها» با یک خط
  برای هر مدل مؤثر توضیح بده.

در پایان پاسخ، دقیقاً یک بلوک json بده:
```json
{"scores": {"نام‌مدل": 8.5, "نام‌مدل۲": 7}, "confidence": 0.8, "open_issues": []}
```
"""

VERIFIER_SYS = """تو «بازبین» نهایی هستی. درخواست کاربر، معیارهای موفقیت و پاسخ پیشنهادی را می‌بینی.
فقط این را بررسی کن: آیا پاسخ (۱) به همه‌ی بخش‌های درخواست جواب داده، (۲) خطای واقعی/ادعای بی‌مدرک دارد،
(۳) قابل اجراست.
خروجی فقط JSON:
{"ok": true/false, "issues": ["..."], "must_fix": ["..."], "confidence": 0..1}
اگر ok=false، در must_fix بنویس پاسخ باید چطور اصلاح شود (کوتاه و اجرایی).
"""

REVISER_SYS = """تو «داور نهایی» هستی و پاسخ قبلی‌ات توسط بازبین ایراد گرفته است.
پاسخ اصلاح‌شده و کامل را بنویس؛ ایرادها را رفع کن و چیزی از دست نده. در پایان همان بلوک json امتیازها را بده.
"""


def _json_from_text(text: str) -> dict:
    """اولین/آخرین شیء JSON را از متن بیرون می‌کشد."""
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", re.S)
    for blob in reversed(fenced):
        try:
            o = json.loads(blob)
            if isinstance(o, dict):
                return o
        except Exception:
            pass
    depth = 0
    start = -1
    for i, ch in enumerate(text or ""):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    o = json.loads(text[start:i + 1])
                    if isinstance(o, dict):
                        return o
                except Exception:
                    pass
                start = -1
    return {}


def _strip_json_block(text: str) -> tuple[str, dict]:
    """بلوک json امتیازها را از پاسخ نهایی جدا می‌کند."""
    data = _json_from_text(text)
    clean = re.sub(r"\n?```(?:json)?\s*\{\s*\"scores\".*?\}\s*```\s*$", "", text or "", flags=re.S).strip()
    if clean == (text or "").strip() and data.get("scores"):
        clean = re.sub(r'\{\s*"scores".*\}\s*$', "", clean, flags=re.S).strip()
    return clean or (text or "").strip(), data


def _heuristic_plan(prompt: str) -> dict:
    p = prompt.lower()
    code = any(k in p for k in ("کد", "code", "python", "اسکریپت", "برنامه", "تابع", "باگ", "خطا", "html", "sql"))
    web = any(k in p for k in ("اخبار", "قیمت", "امروز", "آخرین", "جدید", "news", "2025", "2026", "آمار"))
    return {
        "task_type": "code" if code else "general",
        "difficulty": 3,
        "needs_web": web,
        "needs_tools": code,
        "language": "fa" if re.search(r"[\u0600-\u06FF]", prompt) else "en",
        "plan": ["تحلیل درخواست", "پاسخ مستقل چند مدل", "نقد متقابل", "سنتز نهایی", "بازبینی"],
        "success_criteria": ["پاسخ کامل به همه‌ی بخش‌های درخواست", "بدون ادعای بی‌مدرک", "قابل اجرا/استفاده"],
        "expert_lenses": ["متخصص موضوع", "مهندس اجرا", "منتقد"],
    }


# ------------------------------------------------------------------ ارکستراتور
class Orchestrator:
    def __init__(self, settings: Optional[Settings] = None, memory: Optional[Memory] = None):
        self.s = settings or SETTINGS
        self.m = memory or MEMORY

    # ------------------------------------------------------------- دروازه‌ی اصلی
    async def run_stream(self, prompt: str, session_id: str = "default", mode: str = "panel",
                         forced_models: Optional[list[str]] = None,
                         history: Optional[list[dict]] = None) -> AsyncIterator[dict[str, Any]]:
        """اجرای کامل خط تولید و انتشار رویدادها به‌صورت زنده."""
        q: asyncio.Queue = asyncio.Queue()

        def delta_for(stage_id: str):
            def _emit(t: str) -> None:
                q.put_nowait({"type": "delta", "id": stage_id, "text": t})
            return _emit

        task = asyncio.create_task(
            self._pipeline(prompt, session_id, mode, forced_models, q, delta_for, history or []))

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

    # ----------------------------------------------------------------- خط تولید
    async def _pipeline(self, prompt: str, session_id: str, mode: str,
                        forced_models: Optional[list[str]], q: asyncio.Queue,
                        delta_for, history: list[dict]) -> None:
        t_start = time.time()
        async def emit(ev: dict) -> None:
            await q.put(ev)

        demo = not has_any_model()
        max_panel = {"fast": 1, "panel": self.s.panel_size, "deep": max(self.s.panel_size, 5),
                     "all": 8, "code": max(self.s.panel_size, 3)}.get(mode, self.s.panel_size)
        critiques = 0 if mode == "fast" else (2 if mode in ("deep", "all") else self.s.critique_rounds)
        verify = self.s.verify and mode != "fast"
        use_tools = self.s.use_tools and mode != "fast"

        await emit({"type": "meta", "demo": demo, "mode": mode, "prompt": prompt,
                    "providers": [p.label for p in available_providers()]})

        # ── ۱) مغز راهبر
        sid = "router"
        await emit({"type": "stage", "id": sid, "role": "router", "title": "تحلیل درخواست و طراحی نقشه",
                    "state": "start", "model": ""})
        plan = _heuristic_plan(prompt)
        router_spec = await resolve_role("router", self.s.temperature_router, 900)
        if router_spec:
            router_spec.role = "router"
            await emit({"type": "stage", "id": sid, "state": "model", "model": router_spec.name,
                        "provider": router_spec.provider})
            r = await chat(router_spec, [
                {"role": "system", "content": ROUTER_SYS},
                {"role": "user", "content": self._context(prompt, history)}],
                self.s, delta_for(sid))
            if r.ok:
                got = _json_from_text(r.text)
                if got:
                    plan.update({k: v for k, v in got.items() if v not in (None, "", [])})
                await emit({"type": "stage_end", "id": sid, "state": "done", "seconds": r.seconds,
                            "tokens": r.tokens, "text": json.dumps(plan, ensure_ascii=False, indent=2)})
                await self._store(session_id, prompt, plan, mode, router_spec, r)
            else:
                await emit({"type": "stage_end", "id": sid, "state": "failed", "text": r.error})
        else:
            await emit({"type": "stage_end", "id": sid, "state": "done",
                        "text": json.dumps(plan, ensure_ascii=False, indent=2)})

        task_type = str(plan.get("task_type") or "general")
        lang = plan.get("language") or ("fa" if re.search(r"[\u0600-\u06FF]", prompt) else "en")
        await emit({"type": "plan", "plan": plan})

        run_id = self.m.start_run(session_id, prompt, task_type, mode,
                                  {"plan": plan, "demo": demo})

        # ── ۲) پژوهشگر وب
        research = ""
        if plan.get("needs_web") and use_tools and not demo:
            sid = "scout"
            await emit({"type": "stage", "id": sid, "role": "scout", "title": "پژوهش وب",
                        "state": "start", "model": "ابزار جست‌وجو"})
            box = ToolBox(self._session_dir(session_id))
            queries = await self._scout_queries(prompt)
            chunks: list[str] = []
            for i, query in enumerate(queries[:3]):
                await emit({"type": "tool", "id": sid, "name": "web_search", "args": {"query": query}})
                res = await box.run("web_search", {"query": query})
                chunks.append(f"### جست‌وجو: {query}\n{res}")
                if i == 0:
                    urls = re.findall(r"https?://[^\s)]+", res)[:2]
                    for u in urls:
                        await emit({"type": "tool", "id": sid, "name": "fetch_url", "args": {"url": u}})
                        chunks.append(f"### {u}\n{await box.run('fetch_url', {'url': u})}")
            research = "\n\n".join(chunks)
            await emit({"type": "stage_end", "id": sid, "state": "done",
                        "text": research[:4000] or "چیزی یافت نشد."})

        # ── ۲.۵) بخش خبر / «شبکه‌ی دانش»: چند مدل هرکدام یک زیرسؤال را می‌کاوند
        #         نتیجه‌اش قبل از خبره‌ها به همه داده می‌شود → یعنی همه از یافته‌ی همه خبر دارند.
        broadcast = ""
        if mode in ("deep", "all", "panel") and not demo and self.s.knowledge_broadcast:
            broadcast = await self._broadcast(prompt, plan, delta_for, emit, run_id)

        # ── ۳) انتخاب پنل خبرگان
        panel = await self._choose_panel(task_type, max_panel, forced_models, demo)
        if mode == "fast" and panel:
            panel = panel[:1]
        await emit({"type": "panel", "demo": demo,
                    "models": [dict(p.to_dict(), trust=round(p.temperature, 2)) for p in panel]})

        # ── ۴) خبرگان موازی
        expert_input = [
            {"role": "system", "content": EXPERT_SYS + self._brief(plan, research, use_tools)
             + (f"\n\n## شبکه‌ی دانش (یافته‌ی همکارانت پیش از تو)\n{broadcast}" if broadcast else "")},
            {"role": "user", "content": self._context(prompt, history, for_expert=True)},
        ]
        results = await asyncio.gather(*[
            self._expert(i, spec, expert_input, session_id, use_tools, delta_for, emit, run_id,
                         prompt, plan)
            for i, spec in enumerate(panel)], return_exceptions=True)

        answers: list[dict] = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                await emit({"type": "stage_end", "id": f"expert-{i}", "state": "failed", "text": str(res)})
            elif res:
                answers.append(res)

        if not answers:
            await emit({"type": "error", "message": "هیچ خبره‌ای پاسخ نداد. کلیدهای API و اتصال را بررسی کن."})
            await emit({"type": "final", "text": "اجرا ناکام ماند: هیچ پاسخی از مدل‌ها دریافت نشد.",
                        "panel": [], "seconds": round(time.time() - t_start, 1)})
            return

        # ── ۵) نقد متقابل
        critiques_text: list[str] = []
        anon_map: dict[str, str] = {}
        if critiques and len(answers) > 1:
            letters = "ABCDEFGH"
            anon_map = {letters[i]: a["spec"].id for i, a in enumerate(answers)}
            for ci in range(critiques):
                csid = f"critic-{ci}"
                critic_spec = await resolve_role("critic", 0.3, 1800)
                if not critic_spec:
                    break
                critic_spec.role = "critic"
                await emit({"type": "stage", "id": csid, "role": "critic",
                            "title": f"نقد متقابل دور {ci + 1}", "state": "start", "model": critic_spec.name,
                            "provider": critic_spec.provider})
                order = list(range(len(answers)))
                random.shuffle(order)
                body = "\n\n".join(
                    f"### پاسخ {letters[k]}\n{answers[j]['text']}" for k, j in enumerate(order))
                r = await chat(critic_spec, [
                    {"role": "system", "content": CRITIC_SYS},
                    {"role": "user", "content": f"درخواست کاربر:\n{prompt}\n\nمعیارهای موفقیت:\n"
                                                f"{json.dumps(plan.get('success_criteria', []), ensure_ascii=False)}"
                                                f"\n\n{body}"}], self.s, delta_for(csid))
                if r.ok:
                    crit, parsed = _strip_json_block(r.text)
                    critiques_text.append(crit)
                    self._map_scores(parsed, anon_map, task_type, letters, order, answers)
                    await emit({"type": "stage_end", "id": csid, "state": "done", "text": crit,
                                "seconds": r.seconds})
                    self.m.add_stage(run_id, "critic", critic_spec.model, critic_spec.provider,
                                     crit, r.seconds, True, r.tokens)
                else:
                    await emit({"type": "stage_end", "id": csid, "state": "failed", "text": r.error})

        # ── ۶) داور و سنتز
        jsid = "judge"
        judge_spec = await resolve_role("judge", self.s.temperature_judge, 4096)
        final_text = answers[0]["text"]
        judge_data: dict = {}
        if judge_spec:
            judge_spec.role = "judge"
            await emit({"type": "stage", "id": jsid, "role": "judge", "title": "داوری و سنتز پاسخ نهایی",
                        "state": "start", "model": judge_spec.name, "provider": judge_spec.provider})
            named = "\n\n".join(f"### {a['spec'].name} ({a['spec'].provider})\n{a['text']}" for a in answers)
            crit_block = ("\n\n## نقدها\n" + "\n\n".join(critiques_text)) if critiques_text else ""
            r = await chat(judge_spec, [
                {"role": "system", "content": JUDGE_SYS},
                {"role": "user", "content": f"## درخواست کاربر\n{prompt}\n\n## معیارهای موفقیت\n"
                                            f"{json.dumps(plan.get('success_criteria', []), ensure_ascii=False)}\n"
                                            f"{self._research_block(research)}\n\n## پاسخ خبرگان\n{named}{crit_block}"}],
                self.s, delta_for(jsid))
            if r.ok:
                final_text, judge_data = _strip_json_block(r.text)
                scores = judge_data.get("scores") or {}
                norm_scores = {}
                for a in answers:
                    for k, v in scores.items():
                        if k and (k in a["spec"].name or a["spec"].model.split("/")[-1] in k
                                  or a["spec"].provider in k.lower() or k.strip() == a["spec"].name):
                            norm_scores[a["spec"].id] = v
                if not norm_scores and scores:  # اگر نام‌ها ناخوانا بود، همه را با احتیاط نادیده بگیر
                    norm_scores = {}
                self.m.record_scores(task_type, norm_scores)
                await emit({"type": "stage_end", "id": jsid, "state": "done", "text": final_text,
                            "seconds": r.seconds, "tokens": r.tokens,
                            "scores": [{"model": a["spec"].id, "name": a["spec"].name,
                                        "score": norm_scores.get(a["spec"].id)} for a in answers]})
                self.m.add_stage(run_id, "judge", judge_spec.model, judge_spec.provider,
                                 final_text, r.seconds, True, r.tokens)

        # ── ۷) بازبین و اصلاح
        if verify and not demo:
            vsid = "verifier"
            v_spec = await resolve_role("verifier", 0.1, 900)
            if v_spec:
                v_spec.role = "verifier"
                await emit({"type": "stage", "id": vsid, "role": "verifier", "title": "بازبینی نهایی",
                            "state": "start", "model": v_spec.name, "provider": v_spec.provider})
                r = await chat(v_spec, [
                    {"role": "system", "content": VERIFIER_SYS},
                    {"role": "user", "content": f"## درخواست\n{prompt}\n\n## معیارها\n"
                                                f"{json.dumps(plan.get('success_criteria', []), ensure_ascii=False)}"
                                                f"\n\n## پاسخ پیشنهادی\n{final_text}"}], self.s)
                verdict = _json_from_text(r.text) if r.ok else {}
                await emit({"type": "stage_end", "id": vsid,
                            "state": "done" if r.ok else "failed",
                            "text": json.dumps(verdict or {"raw": (r.text or r.error)[:600]},
                                               ensure_ascii=False, indent=2)})
                if r.ok and verdict.get("ok") is False and verdict.get("must_fix") and judge_spec:
                    rid = "reviser"
                    await emit({"type": "stage", "id": rid, "role": "judge", "title": "اصلاح بر اساس بازبینی",
                                "state": "start", "model": judge_spec.name})
                    rr = await chat(judge_spec, [
                        {"role": "system", "content": REVISER_SYS},
                        {"role": "user", "content": f"## درخواست\n{prompt}\n\n## پاسخ قبلی\n{final_text}\n\n"
                                                    f"## ایرادهای بازبین\n"
                                                    f"{json.dumps(verdict.get('must_fix'), ensure_ascii=False)}"
                                                    f"\n\n## سایر ایرادها\n"
                                                    f"{json.dumps(verdict.get('issues', []), ensure_ascii=False)}"}],
                        self.s, delta_for(rid))
                    if rr.ok:
                        fixed, d2 = _strip_json_block(rr.text)
                        final_text = fixed
                        if d2.get("scores"):
                            judge_data = d2
                        await emit({"type": "stage_end", "id": rid, "state": "done", "text": final_text,
                                    "seconds": rr.seconds})

        # ── پایان
        seconds = round(time.time() - t_start, 1)
        self.m.finish_run(run_id, final_text, {"plan": plan, "seconds": seconds,
                                               "models": [a["spec"].id for a in answers],
                                               "judge": judge_data})
        await emit({"type": "final", "text": final_text,
                    "panel": [{"id": a["spec"].id, "name": a["spec"].name, "provider": a["spec"].provider,
                               "family": family_of(a["spec"].model), "seconds": a["seconds"],
                               "tokens": a["tokens"], "tools": a["tools"]} for a in answers],
                    "plan": plan, "run_id": run_id, "seconds": seconds,
                    "tokens": sum(a["tokens"] for a in answers),
                    "confidence": judge_data.get("confidence"),
                    "open_issues": judge_data.get("open_issues") or []})

    # ------------------------------------------------------------- اجزای کمکی
    async def _broadcast(self, prompt: str, plan: dict, delta_for, emit, run_id: int) -> str:
        """چند مدل مختلف، موازی، هرکدام یک زاویه‌ی متفاوت را می‌کاوند؛ جمع‌بندی به همه‌ی خبره‌ها می‌رسد."""
        probes = [
            ("واقعیت‌ها و داده‌ها", "فقط یافته‌های عینی و عددی مرتبط را بنویس: چه چیزهایی مسلم است، "
                                  "چه اعدادی مهم است، چه چیزی قابل اندازه‌گیری است. بیش از ۱۲ خط ننویس."),
            ("تجربه‌ی عملی", "تجربه‌ی عملی و میان‌بُرهای واقعی همین کار را بنویس: چه چیزی در عمل جواب "
                             "می‌دهد، چه چیزی وقت تلف‌کردن است. بیش از ۱۲ خط ننویس."),
            ("خطرها و لبه‌ها", "خطرها، حالت‌های مرزی، سوءبرداشت‌های رایج و جاهایی که کار می‌شکند را فهرست کن. "
                              "بیش از ۱۲ خط ننویس."),
            ("راه‌حل رقیب", "یک راه‌حل متفاوت از راه‌حل بدیهی پیشنهاد بده و بگو کجا از راه‌حل معمول بهتر است. "
                           "بیش از ۱۲ خط ننویس."),
        ]
        n = max(2, min(int(getattr(self.s, "broadcast_size", 3) or 3), len(probes), self.s.panel_size))
        specs: list[ModelSpec] = []
        seen: set[str] = set()
        for role in ("expert", "expert2", "expert"):
            sp = await resolve_role(role, 0.5, 1100, exclude=seen)
            if not sp or sp.id in seen:
                continue
            seen.add(sp.id)
            sp.role = role
            specs.append(sp)
            if len(specs) >= n:
                break
        if not specs:
            return ""
        await emit({"type": "stage", "id": "knowledge", "role": "knowledge",
                    "title": "شبکه‌ی دانش (کاوش موازی چند مدل)", "state": "start", "model": ""})
        await emit({"type": "panel", "demo": False, "stage": "knowledge",
                    "models": [dict(sp.to_dict()) for sp in specs]})

        async def one(i: int, sp: ModelSpec) -> dict:
            name, ask = probes[i % len(probes)]
            msgs = [{"role": "system", "content": "تو یک کاوش‌گر تخصصی هستی. فارسی، دقیق و بی‌حاشیه."},
                    {"role": "user", "content": f"درخواست کاربر:\n{prompt[:2500]}\n\n"
                                                f"چیزی که برنامه نوشته: {json.dumps(plan, ensure_ascii=False)[:700]}\n\n"
                                                f"مأموریت تو: {ask}"}]
            r = await chat(sp, msgs, self.s, delta_for(f"knowledge-{i}"))
            if not r.ok:
                return {}
            self.m.add_stage(run_id, "broadcast", sp.model, sp.provider, r.text, r.seconds, True,
                             r.tokens)
            return {"name": name, "model": sp.name, "provider": sp.provider, "text": r.text.strip()}

        got = [x for x in await asyncio.gather(*[one(i, sp) for i, sp in enumerate(specs)],
                                               return_exceptions=True) if isinstance(x, dict) and x]
        if not got:
            await emit({"type": "stage_end", "id": "knowledge", "state": "failed",
                        "text": "کاوش موازی نتیجه نداد."})
            return ""
        body = "\n\n".join(f"### {g['name']} — {g['model']}\n{g['text'][:1400]}" for g in got)
        await emit({"type": "stage_end", "id": "knowledge", "state": "done", "text": body[:4000],
                    "models": [g["model"] for g in got]})
        return body

    def _session_dir(self, session_id: str) -> Path:
        d = WORKSPACE / re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "default")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _brief(self, plan: dict, research: str, use_tools: bool) -> str:
        out = ["\n\n## نقشه‌ی اجرا (از مغز راهبر)"]
        for i, step in enumerate(plan.get("plan", []) or [], 1):
            out.append(f"{i}. {step}")
        if plan.get("success_criteria"):
            out.append("\n## معیارهای موفقیت\n- " + "\n- ".join(plan["success_criteria"]))
        if use_tools:
            out.append("\n" + tool_manual())
        return "\n".join(out)

    def _research_block(self, research: str) -> str:
        return f"\n## یافته‌های پژوهش وب\n{research[:5000]}\n" if research else ""

    def _context(self, prompt: str, history: list[dict], for_expert: bool = False) -> str:
        if not history:
            return prompt
        lines = ["## گفت‌وگوی قبلی همین نشست (برای زمینه)"]
        for h in history[-4:]:
            q = (h.get("prompt") or "")[:400]
            a = (h.get("final") or "")[:700]
            lines.append(f"کاربر: {q}\nسیستم: {a}")
        lines.append("\n## درخواست فعلی کاربر\n" + prompt)
        return "\n\n".join(lines)

    async def _scout_queries(self, prompt: str) -> list[str]:
        spec = await resolve_role("router", 0.2, 300)
        if spec:
            spec.role = "router"
            r = await chat(spec, [
                {"role": "system", "content": "سه عبارت جست‌وجوی وب (فقط JSON آرایه‌ی رشته‌ها) بده که "
                                              "بهترین اطلاعات را برای پاسخ به درخواست کاربر پیدا کند. "
                                              'خروجی فقط مثل: ["...","...","..."]'},
                {"role": "user", "content": prompt[:2000]}], self.s)
            if r.ok:
                m = re.search(r"\[.*\]", r.text, re.S)
                if m:
                    try:
                        arr = json.loads(m.group(0))
                        if isinstance(arr, list) and arr:
                            return [str(x) for x in arr][:3]
                    except Exception:
                        pass
        return [prompt[:180]]

    async def _choose_panel(self, task_type: str, size: int,
                            forced: Optional[list[str]], demo: bool) -> list[ModelSpec]:
        if demo:
            mock = [("openai", "gpt-5 (نمایشی)"), ("anthropic", "claude-sonnet-4.5 (نمایشی)"),
                    ("gemini", "gemini-2.5-pro (نمایشی)"), ("xai", "grok-4 (نمایشی)"),
                    ("deepseek", "deepseek-v3 (نمایشی)")]
            return [ModelSpec(p, m, role="expert", reason="demo") for p, m in mock[:max(size, 2)]]

        specs: list[ModelSpec] = []
        if forced:
            for item in forced:
                if ":" in item:
                    pid, model = item.split(":", 1)
                    specs.append(ModelSpec(pid, model, role="expert"))
        if not specs:
            seen: set[str] = set()
            for off in range(7):
                sp = await resolve_role("expert", self.s.temperature_expert, 2600, exclude=seen,
                                        offset=off)
                if sp and sp.id not in seen:
                    seen.add(sp.id)
                    specs.append(sp)
            if len(specs) < 2:
                for off in range(4):
                    sp = await resolve_role("expert2", self.s.temperature_expert, 2600,
                                            exclude=seen, offset=off)
                    if sp and sp.id not in seen:
                        seen.add(sp.id)
                        specs.append(sp)

        trust = self.m.model_trust(task_type)
        # امتیاز پایه + تنوع خانواده‌ها؛ مدل‌هایی که در این نوع کار بهتر بوده‌اند بالاتر می‌آیند
        for sp in specs:
            sp.temperature = float(trust.get(sp.id, 6.5))
        specs.sort(key=lambda s: -s.temperature)
        out: list[ModelSpec] = []
        # اگر فقط یک پرووایدر کلید دارد، سقف «دو مدل از هر پرووایدر» را برمی‌داریم
        # تا پنل واقعاً پُر شود (مثلاً همه‌ی خبره‌ها از OpenRouter).
        cap = 2 if len(available_providers()) > 1 else max(size, 2)
        per_provider: dict[str, int] = {}
        for sp in specs:
            if per_provider.get(sp.provider, 0) >= cap:
                continue
            out.append(sp)
            per_provider[sp.provider] = per_provider.get(sp.provider, 0) + 1
            if len(out) >= size:
                break
        for sp in specs:            # پُر کردن باقی پنل با هر مدل موجود دیگری
            if len(out) >= size:
                break
            if sp not in out:
                out.append(sp)
        for sp in out:
            sp.temperature = self.s.temperature_expert
            sp.reason = f"اعتماد تاریخی: {trust.get(sp.id, 6.5):.1f}/10"
        return out

    async def _expert(self, idx: int, spec: ModelSpec, messages: list[dict], session_id: str,
                      use_tools: bool, delta_for, emit, run_id: int, prompt: str,
                      plan: dict) -> Optional[dict]:
        sid = f"expert-{idx}"
        lens = (plan.get("expert_lenses") or [])
        angle = lens[idx % len(lens)] if lens else "متخصص عمومی"
        await emit({"type": "stage", "id": sid, "role": "expert",
                    "title": f"خبره {idx + 1} — {angle}", "state": "start",
                    "model": spec.name, "provider": spec.provider, "lens": angle})
        msgs = [dict(m) for m in messages]
        msgs[0] = {"role": "system", "content": messages[0]["content"] +
                   f"\n\n## زاویه‌ی تخصصی تو در این کار\n{angle}\nنقش تو: {spec.reason}"}
        text, tools_used, tokens, seconds, ok, err = "", [], 0, 0.0, False, ""
        for rnd in range(self.s.max_tool_rounds if use_tools else 1):
            r: ChatResult = await chat(spec, msgs, self.s, delta_for(sid))
            seconds += r.seconds
            tokens += r.tokens
            if not r.ok:
                err = r.error
                break
            ok = True
            calls = extract_tool_calls(r.text) if use_tools else []
            if not calls:
                text = r.text
                break
            visible = strip_tool_blocks(r.text)
            if visible:
                text = visible
            msgs.append({"role": "assistant", "content": r.text})
            results = []
            fin = None
            box = ToolBox(self._session_dir(session_id))
            for c in calls[:3]:
                await emit({"type": "tool", "id": sid, "name": c["name"], "args": c["args"]})
                res = await box.run(c["name"], c["args"])
                tools_used.append({"name": c["name"], "args": c["args"], "result": res[:1200]})
                await emit({"type": "tool_result", "id": sid, "name": c["name"], "result": res[:2000]})
                if res.startswith("__FINISH__"):
                    fin = res.replace("__FINISH__", "", 1)
                results.append(f"[نتیجه‌ی {c['name']}]\n{res}")
            if fin is not None:
                text = fin or text
                break
            msgs.append({"role": "user", "content": "نتیجه‌ی ابزارها:\n\n" + "\n\n".join(results) +
                                                    "\n\nحالا ادامه بده و پاسخ نهایی را بنویس "
                                                    "(اگر کار تمام است با ابزار finish بده)."})
            if rnd == (self.s.max_tool_rounds if use_tools else 1) - 1 and not text:
                f = await chat(spec, msgs + [{"role": "user", "content": "پاسخ نهایی را بدون ابزار بنویس."}],
                               self.s, delta_for(sid))
                text = f.text
                seconds += f.seconds
                tokens += f.tokens
                ok = f.ok
        text = strip_tool_blocks(text or "") or text
        await emit({"type": "stage_end", "id": sid, "state": "done" if ok and text else "failed",
                    "text": text or err, "seconds": round(seconds, 2), "tokens": tokens,
                    "tools": [t["name"] for t in tools_used]})
        self.m.add_stage(run_id, "expert", spec.model, spec.provider, text or err,
                         seconds, bool(ok and text), tokens)
        if not text:
            return None
        return {"spec": spec, "text": text, "seconds": round(seconds, 2), "tokens": tokens,
                "tools": [t["name"] for t in tools_used]}

    def _map_scores(self, parsed: dict, anon_map: dict[str, str], task_type: str,
                    letters: str, order: list[int], answers: list[dict]) -> None:
        scores = (parsed or {}).get("scores") or {}
        if not isinstance(scores, dict) or not scores:
            return
        mapped: dict[str, float] = {}
        for k, v in scores.items():
            letter = str(k).strip().upper()[:1]
            if letter in anon_map:
                mapped[anon_map[letter]] = v
            else:
                for a in answers:  # اگر مدل با نام صدا زده بود
                    if a["spec"].name.split()[0].lower() in str(k).lower():
                        mapped[a["spec"].id] = v
        self.m.record_scores(task_type, mapped, count_win=False)

    async def _store(self, session_id: str, prompt: str, plan: dict, mode: str,
                     spec: ModelSpec, r: ChatResult) -> None:
        self.m.ensure_session(session_id, prompt[:60])


# ------------------------------------------------------------- اجرای یک‌باره (CLI)
async def run_once(prompt: str, session_id: str = "cli", mode: str = "panel",
                   settings: Optional[Settings] = None, printer: str | None = "summary") -> str:
    """اجرای یک پرامپت در CLI.  printer: "summary" (پیش‌فرض) | "live" (استریم خام) | None"""
    orch = Orchestrator(settings)
    final = ""
    ICON = {"router": "🧭", "scout": "🌐", "expert": "🧠", "critic": "🔍",
            "judge": "⚖️", "verifier": "✅"}
    async for ev in orch.run_stream(prompt, session_id=session_id, mode=mode):
        t = ev["type"]
        if not printer:
            if t == "final":
                final = ev["text"]
            continue
        if t == "meta":
            print(f"\n{'═' * 66}\n🧠 MEGA-AI | حالت {ev['mode']} | "
                  f"{'حالت نمایشی (بدون کلید)' if ev['demo'] else ' · '.join(ev['providers'])}\n{'═' * 66}")
        elif t == "stage" and ev.get("state") == "start":
            icon = ICON.get(ev.get("role", ""), "•")
            line = f"\n{icon} {ev.get('title', '')}"
            if ev.get("model"):
                line += f"  [{ev['model']}]"
            print(line)
            if printer == "live":
                print("   ", end="", flush=True)
        elif t == "delta" and printer == "live":
            print(ev["text"], end="", flush=True)
        elif t == "tool":
            print(f"   🔧 {ev['name']}: {json.dumps(ev['args'], ensure_ascii=False)[:140]}")
        elif t == "stage_end" and printer == "summary":
            txt = (ev.get("text") or "").strip()
            if ev.get("state") == "failed":
                print(f"   ⚠️  ناکام: {txt[:200]}")
            elif txt:
                body = textwrap.indent(textwrap.fill(txt, 100), "   ")
                print(body[:4000])
        elif t == "panel":
            names = " · ".join(m["name"] for m in ev.get("models", []))
            print(f"\n👥 پنل خبرگان: {names}")
        elif t == "error":
            print(f"\n⛔ {ev['message']}")
        elif t == "final":
            final = ev["text"]
    return final
