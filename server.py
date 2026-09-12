"""
MEGA-AI  |  سرور وب (FastAPI)
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
from mega.config import (ENV_PATH, SETTINGS, WEB_DIR, WORKSPACE, configured_providers, key_status,
                         has_real_keys, real_configured_providers,
                         load_env, save_keys, PROVIDERS)
from mega.media import THEMES, VOICES, make_ad, make_image, make_video, stt, tts
from mega.memory import MEMORY
from mega.orchestrator import Orchestrator
from mega.providers import clear_cache, health_check_all, list_models, test_provider
from mega.skills import SkillBox, installed_skills, update_libraries
from mega.telegram_bot import TelegramBot

app = FastAPI(title="MEGA-AI", docs_url="/api/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

load_env()
STATE: dict = {"settings": SETTINGS}


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
    """اگر هیچ کلید واقعی نیست، مدل نمایشی داخلی را وصل کن تا سیستم کار کند."""
    from mega import demo_model
    if not configured_providers():
        demo_model.enable(app, _listen_port())


@app.get("/")
async def index():
    """پنل کاربری آسان (پیش‌فرض)."""
    simple = WEB_DIR / "simple.html"
    return FileResponse(simple if simple.exists() else WEB_DIR / "index.html")


@app.get("/advanced")
async def advanced():
    """رابط کامل حرفه‌ای."""
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health")
async def health():
    from mega import demo_model
    s = STATE["settings"]
    return {
        "ok": True,
        "demo": not has_real_keys(),
        "demo_model": demo_model.BRIDGE["active"],
        "providers": key_status(),
        "active": [p.id for p in real_configured_providers()],
        "settings": {k: getattr(s, k) for k in s.__dataclass_fields__},
        "stats": MEMORY.stats(),
    }


@app.post("/api/keys")
async def set_keys(payload: dict):
    from mega import demo_model
    save_keys({k.upper(): str(v) for k, v in payload.items() if isinstance(k, str)})
    if configured_providers():
        demo_model.disable()          # کلید واقعی آمد → مدل نمایشی کنار می‌رود
    return {"ok": True, "active": [p.id for p in configured_providers()],
            "providers": key_status(), "demo_model": demo_model.BRIDGE["active"]}


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


@app.get("/api/history")
async def history(session: str = "", limit: int = 20):
    return {"ok": True, "sessions": MEMORY.sessions(), "leaderboard": MEMORY.leaderboard(),
            "stats": MEMORY.stats()}


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
async def files(path: str):
    root = WORKSPACE.resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        return JSONResponse({"ok": False, "error": "فایل پیدا نشد"}, status_code=404)
    return FileResponse(target, filename=target.name)


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


_maybe_bridge()


if __name__ == "__main__":
    import uvicorn
    port = _listen_port()
    host = os.environ.get("MEGA_HOST", "0.0.0.0")
    shown = "localhost" if host in ("127.0.0.1", "localhost") else host
    print(f"\n  MEGA-AI آماده است →  http://{shown}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")
