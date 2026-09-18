# -*- coding: utf-8 -*-
"""تست‌های رابط کاربری: مطمئن می‌شویم هیچ وصله‌ای تابع/دکمه‌ای را گم نکند.

این تست‌ها بعد از هر تغییر اجرا می‌شوند تا خطاهایی مثل «loadFiles is not defined»
هرگز دوباره به سرور کاربر نرسد.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
PAGES = ["index.html", "simple.html", "terminal.html", "tv.html", "more.html"]

REQUIRED_INDEX_FUNCS = [
    "runAgent", "handleAgent", "loadFiles", "loadStudioFiles", "runCouncil",
    "stageEl", "mediaBox", "togglePrev", "fileIcon", "fmtSize", "md",
    "goTab", "loadDash", "loadHealth", "loadSkills", "loadOptions", "stripTools",
]
REQUIRED_IDS = [
    "agentChat", "goal", "agentRun", "agentStop", "agentStatus", "fileList",
    "refreshFiles", "agentPlan", "send", "stop", "final", "copyFinal", "modes",
    "fileList", "studioFiles", "nav", "statusBadge", "verBadge",
]


def _ids(html: str) -> set[str]:
    return set(re.findall(r'id="([A-Za-z0-9_-]+)"', html))


def _js(html: str) -> str:
    return "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))


@pytest.mark.parametrize("page", PAGES)
def test_page_exists(page: str) -> None:
    assert (WEB / page).is_file(), f"{page} نیست"


@pytest.mark.parametrize("page", PAGES)
def test_every_selector_has_matching_element(page: str) -> None:
    """هر $("#x") باید عنصر واقعی داشته باشد — وگرنه در مرورگر «خطا» می‌دهد."""
    html = (WEB / page).read_text(encoding="utf-8")
    ids = _ids(html)
    js = _js(html)
    refs = set(re.findall(r'\$\("#([A-Za-z0-9_-]+)"\)', js))
    refs |= set(re.findall(r'\$\$\("#([A-Za-z0-9_-]+)', js))
    missing = sorted(refs - ids)
    assert not missing, f"{page}: این شناسه‌ها در کد هستند ولی در صفحه نیستند: {missing}"


def test_index_required_functions_exist() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = _js(html)
    missing = [f for f in REQUIRED_INDEX_FUNCS
               if not re.search(rf"function\s+{f}\s*\(", js)]
    assert not missing, f"این توابع در index.html نیستند: {missing}"


def test_index_required_ids_exist() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    missing = [i for i in REQUIRED_IDS if i not in _ids(html)]
    assert not missing, f"این شناسه‌ها در index.html نیستند: {missing}"


def test_no_tool_json_visible_in_chat_pages() -> None:
    """JSON خام ابزارها نباید در چت نشان داده شود."""
    for page in ("index.html", "simple.html", "terminal.html"):
        js = _js((WEB / page).read_text(encoding="utf-8"))
        assert "stripTools" in js, f"{page}: پاک‌سازی JSON ابزار نیست"


def test_tool_fence_filter_behavior() -> None:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mega.tools import strip_tool_blocks, ToolFenceFilter

    src = 'سلام\n\n```tool\n{"name": "shell", "args": {"command": "dir"}}\n```\n\nتمام شد.'
    out = strip_tool_blocks(src)
    assert "shell" not in out and "dir" not in out and "سلام" in out and "تمام شد" in out

    got: list[str] = []
    f = ToolFenceFilter(got.append)
    for i in range(0, len(src), 5):
        f.feed(src[i:i + 5])
    f.flush()
    joined = "".join(got)
    assert "```" not in joined and '"args"' not in joined

    keep = 'ببین:\n\n```python\nprint(1)\n```\n\nخوب بود.'
    assert "```python" in strip_tool_blocks(keep)


def test_echo_redirect_windows() -> None:
    """«echo … > file» باید در همه‌ی حالت‌ها به (متن، مسیر) تبدیل شود."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mega.skills import _redirect_split

    assert _redirect_split("""echo '<b>hi</b>' > index.html""") == ("<b>hi</b>", "index.html", False)
    assert _redirect_split('echo "x" >> a.txt') == ("x", "a.txt", True)
    assert _redirect_split("dir > out.txt") is None


def test_inapp_viewer_present() -> None:
    """پنجرهٔ «نمایش در برنامه» باید در صفحه‌ها باشد (HTML، متن، عکس)."""
    for page in ("index.html", "simple.html"):
        html = (WEB / page).read_text(encoding="utf-8")
        js = _js(html)
        assert 'id="viewer"' in html, f"{page}: پنجرهٔ پیش‌نمایش نیست"
        for fn in ("openViewer", "closeViewer", "kindOf", "dlUrl"):
            assert fn in js, f"{page}: تابع {fn} نیست"


def test_files_route_serves_inline() -> None:
    """مسیر /files پیش‌فرض باید inline باشد (تا در برنامه باز شود) و با dl=1 دانلود."""
    import re
    src = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    start = src.index('@app.get("/files/{path:path}")')
    block = src[start + 10:]
    block = block[:block.index("@app.")]
    assert "dl: int = 0" in block, "پارامتر dl نیست"
    assert "FileResponse(target, filename=target.name" in block, "حالت دانلود نیست"
    assert block.count("FileResponse") >= 2, "حالت inline/دانلود جدا نشده"


def test_media_shows_inline() -> None:
    """عکس/کلیپ باید بلافاصله «بالا» نشان داده شود، نه فقط دکمهٔ دانلود."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = _js(html)
    assert '<video src="${url}"' in js or "<video src=\"${url}\"" in js, "ویدیو داخل صفحه ساخته نمی‌شود"
    assert '<img src="${url}"' in js or "<img src=\"${url}\"" in js, "تصویر داخل صفحه ساخته نمی‌شود"
    assert ".media img" in html and ".media video" in html, "استایل نمایش رسانه نیست"
    assert "class=\"media\"" in js or "class=\"media\"" in html, "کادر media نیست"


def test_file_card_shows_media_first() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = _js(html)
    block = js[js.index("function fileCard("):]
    block = block[:block.index("function lastStepEl(")]
    assert 'if(kind === "media")' in block, "کارت فایل رسانه‌ای مسیر نمایش بالا ندارد"
    assert 'class="media"' in block, "کادر media در کارت فایل نیست"


def test_history_ui_present() -> None:
    """تاریخچه و پاک‌سازی باید در رابط باشد."""
    for page in ("index.html", "simple.html"):
        html = (WEB / page).read_text(encoding="utf-8")
        js = _js(html)
        assert 'id="histModal"' in html, f"{page}: پنجرهٔ تاریخچه نیست"
        for fn in ("histOpen", "histReload", "histDelRun", "histDelSession", "histClearAll", "clearChat"):
            assert fn in js, f"{page}: تابع {fn} نیست"


def test_update_ui_present() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = _js(html)
    assert 'id="updModal"' in html, "پنجرهٔ آپدیت نیست"
    for fn in ("updOpen", "doUpdate", "doRestart"):
        assert fn in js, f"تابع {fn} نیست"


def test_history_endpoints() -> None:
    src = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    for route in ('@app.get("/api/history")', '@app.post("/api/history")',
                  '@app.post("/api/update")', '@app.post("/api/restart")',
                  '@app.get("/api/version")'):
        assert route in src, f"مسیر {route} نیست"


def test_updater_safe_copy() -> None:
    """آپدیت نباید به .env و data و workspace دست بزند."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mega import updater
    assert ".env" in updater.KEEP_FILES
    for d in ("data", "workspace", ".venv", ".git"):
        assert d in updater.KEEP_DIRS, f"{d} در فهرست محفوظ‌ها نیست"
    assert len(updater.MIRRORS) >= 3, "آینه‌های دانلود کم است"


def test_restart_script_targets_only_self() -> None:
    """اسکریپت ری‌استارت باید فقط PID خودمان را ببندد (ربات MT5 دست نخورد)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mega import updater
    win = updater._script(False, 12345)
    posix = updater._script(True, 12345)
    assert "12345" in win and "taskkill /F /PID 12345" in win
    assert "python.exe" not in win.replace("python start_vps.py", ""), "نباید همهٔ پایتون‌ها را ببندد"
    assert "kill -TERM 12345" in posix


def test_big_brain_default() -> None:
    """مغز پیش‌فرض باید بزرگ‌ترین مدل در دسترس باشد (Nemotron-3-120B)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mega.config import PROVIDERS, ROLE_CANDIDATES
    models = PROVIDERS["cloudflare"].default_models
    assert models[0] == "@cf/nvidia/nemotron-3-120b-a12b", f"مدل اول = {models[0]}"
    assert "@cf/openai/gpt-oss-120b" in models[:2], "پشتیبان ۱۲۰ میلیاردی نیست"
    for role in ("agent", "expert", "balanced"):
        cf = [prefs for pid, prefs in ROLE_CANDIDATES.get(role, []) if pid == "cloudflare"]
        if cf:
            assert cf[0][0] == "@cf/nvidia/nemotron-3-120b-a12b", f"نقش {role} → {cf[0][:1]}"


def test_reasoning_models_handled() -> None:
    """مدل‌های استدلالی: کف توکن + جدا نگه‌داشتن «فکر» از متن پاسخ."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mega.providers import is_reasoning, fit_tokens, _extract
    assert is_reasoning("@cf/openai/gpt-oss-120b")
    assert is_reasoning("@cf/nvidia/nemotron-3-120b-a12b")
    assert not is_reasoning("@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    assert fit_tokens("@cf/openai/gpt-oss-120b", 256) >= 900
    assert fit_tokens("@cf/meta/llama-3.1-8b-instruct-fp8", 256) == 256

    # فقط فکر (reasoning) → نباید داخل متن کاربر برود
    acc, rea = [], []
    data = {"choices": [{"delta": {"reasoning": "Let me think in English..."}}]}
    _extract("openai", data, acc, rea)
    assert not acc and rea, "فکر مدل به متن کاربر نشت کرد"
    # پاسخ واقعی → متن
    data2 = {"choices": [{"delta": {"content": "سلام"}}]}
    _extract("openai", data2, acc, rea)
    assert acc == ["سلام"]
    # پاسخ غیراستریم خالی + reasoning → متن نهایی خالی نماند
    acc2, rea2 = [], []
    _extract("openai", {"choices": [{"message": {"reasoning": "فکر"}}]}, acc2, rea2)
    assert (acc2 or rea2), "پاسخ خالی برگشت"


def test_history_inline_panel() -> None:
    """تاریخچه باید داخل خود صفحه دیده شود (نه فقط پنجرهٔ مخفی) و دکمهٔ پاک کردن داشته باشد."""
    for page in ("index.html", "simple.html"):
        html = (WEB / page).read_text(encoding="utf-8")
        js = _js(html)
        assert 'id="histInline"' in html, f"{page}: پنل تاریخچهٔ کنار صفحه نیست"
        assert 'id="histCount"' in html, f"{page}: شمارندهٔ تاریخچه نیست"
        for fn in ("histItemHTML", "renderInlineHist", "histUse", "toast"):
            assert fn in js, f"{page}: تابع {fn} نیست"
        assert "histClearAll()" in html, f"{page}: دکمهٔ پاک کردن همه نیست"


def test_history_nav_button() -> None:
    """دکمهٔ تاریخچه باید در نوار بالا باشد تا پیدا شود."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    nav = html[html.index('<nav id="nav">'):html.index("</nav>")]
    assert "history" in nav, "تب تاریخچه در نوار بالا نیست"
    assert "updOpen()" in nav, "دکمهٔ آپدیت در نوار بالا نیست"


def test_console_updater_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    s = (root / "update_self.py").read_text(encoding="utf-8")
    assert "MIRRORS" in s and "--restart" in s and "taskkill" in s, "آپدیت‌کنندهٔ مستقل کامل نیست"


def test_history_tab_present() -> None:
    """تب تاریخچه: جست‌وجو + حذف + استفادهٔ دوباره."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = _js(html)
    assert 'id="tab-history"' in html, "بخش تب تاریخچه نیست"
    assert 'id="histTabList"' in html and 'id="histQ"' in html, "لیست/جست‌وجوی تاریخچه نیست"
    assert "histTabRender" in js, "رندر تب تاریخچه نیست"
    assert '"history"' in js.replace("'", '"') and "tab-history" in html, "تب تاریخچه در فهرست تب‌ها نیست"


def test_dashboard_has_history_card() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="dashHist"' in html, "کارت تاریخچه در داشبورد نیست"


def test_brain_badge() -> None:
    for page in ("index.html", "simple.html"):
        html = (WEB / page).read_text(encoding="utf-8")
        assert 'id="brainBadge"' in html, f"{page}: نشان مغز نیست"
    src = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    assert "_brain_label" in src and '"brain": _brain_label()' in src


def test_huge_models_registered() -> None:
    """مدل‌های ۲۰۰ میلیاردی+ باید در فهرست باشند (Groq/OpenRouter)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mega.config import PROVIDERS
    groq = PROVIDERS["groq"].default_models
    openrouter = PROVIDERS["openrouter"].default_models
    # توجه: Groq مدل‌های ۴۰۰ میلیاردی/۱ تریلیونی را از پلن رایگان برداشته؛
    # بزرگ‌ترین مدل رایگانش الان gpt-oss-120b است (با کلید واقعی تست شد).
    assert any("gpt-oss-120b" in m for m in groq), "قوی‌ترین مدل رایگان Groq نیست"
    assert any("compound" in m for m in groq), "سیستم ترکیبی Groq نیست"
    # فهرست رایگان OpenRouter هم عوض شده: الان بزرگ‌ترین رایگانش ۵۵۰ میلیارد است
    assert any("nemotron-3-ultra-550b" in m for m in openrouter), "۵۵۰ میلیاردی رایگان در OpenRouter نیست"
    assert any("nemotron-3-super-120b" in m for m in openrouter), "۱۲۰ میلیاردی رایگان در OpenRouter نیست"


def test_safe_arrays() -> None:
    """هیچ‌جا نباید (چیزی || []).map باشد — مدل ممکن است رشته بفرستد و خطا بدهد."""
    import re as _re
    for page in ("index.html", "simple.html"):
        html = (WEB / page).read_text(encoding="utf-8")
        js = _js(html)
        assert "function asArr(" in js, f"{page}: تابع امن asArr نیست"
        bad = _re.findall(r"\((?:[A-Za-z_$][\w.$?]*\.)?[A-Za-z_$][\w.$?]*\s*\|\|\s*\[\]\)\s*\.map", js)
        assert not bad, f"{page}: الگوی پرخطر {bad[:3]}"
        assert "(args.files || []).map" not in js, "خطای args.files برگشته!"


def test_asarr_behavior() -> None:
    """asArr باید رشته، آرایه، null و JSON-رشته را امن مدیریت کند (باگ «map is not a function»)."""
    import json as _json
    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node")
    if not node:
        return
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = _js(html)
    i = js.index("function asArr(")
    fn = js[i:js.index("\n}\n", i) + 3]
    probe = [
        'const cases=[[],null,undefined,"","a.txt","a.txt, b.txt","[\\"x\\",\\"y\\"]",5,{a:1}];',
        "console.log(JSON.stringify(cases.map(c=>asArr(c).length)));",
        'console.log(JSON.stringify(asArr("a.txt, b.txt")));',
        "console.log(JSON.stringify(asArr('[\"x\",\"y\"]')));",
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(fn + "\n" + "\n".join(probe) + "\n")
        path = f.name
    out = subprocess.run([node, path], capture_output=True, text=True).stdout.strip().splitlines()
    Path(path).unlink(missing_ok=True)
    assert out and _json.loads(out[0]) == [0, 0, 0, 0, 1, 2, 2, 1, 1], out
    assert _json.loads(out[1]) == ["a.txt", "b.txt"], out
    assert _json.loads(out[2]) == ["x", "y"], out




def test_brain_tab() -> None:
    """تب مغز: نمایش مغز فعال + کلید Groq/OpenRouter با تست واقعی."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = _js(html)
    for need in ('id="tab-brain"', 'id="brainNow"', 'id="groqKey"', 'id="orKey"',
                 'console.groq.com/keys', 'openrouter.ai/keys'):
        assert need in html, f"تب مغز ناقص است: {need} نیست"
    for fn in ("loadBrainTab", "brainSave"):
        assert fn in js, f"تابع {fn} نیست"


def test_agent_null_guard() -> None:
    """bug واقعی: کارت «پایان کار» کادر .res ندارد → قبلاً خطای null.textContent می‌داد."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'LAST_TOOL_CARD && LAST_TOOL_CARD.querySelector(".res")' in html, "نگهبان tool_result نیست"
    assert 'if(LAST_TOOL_CARD){\n        const r = LAST_TOOL_CARD.querySelector(".res")' not in html, \
        "نگهبان قدیمی برگشته"
    assert "try{ handleAgent(ev, stepEl, toolCount); }catch" in html, "رویداد کارگزار محافظت نشده"
    assert 'LAST_TOOL_CARD = null; return card;' in html, "کارت پایان کار باید از LAST_TOOL_CARD بیرون باشد"


def test_viewer_back_forward_and_html_runs() -> None:
    """پنجرهٔ پیش‌نمایش: دکمه‌های قبلی/بعدی + کش محتوا + اجرای واقعی HTML داخل برنامه."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = _js(html)
    for i in ("vBack", "vFwd", "vIdx", "vRun"):
        assert f'id="{i}"' in html, f"دکمهٔ {i} نیست"
    for fn in ("vShow", "vNav", "vRender", "vRerun", "vSync", "vFind"):
        assert f"function {fn}" in js or f"async function {fn}" in js, f"تابع {fn} نیست"
    assert "srcdoc" in js, "HTML با srcdoc داخل برنامه اجرا نمی‌شود"
    assert 'sandbox' in js and "allow-scripts" in js, "iframe اجازهٔ اجرای اسکریپت ندارد"
    assert "VIEW_HIST" in js and "it.text = t" in js, "کش محتوا برای رفت/برگشت نیست"
    assert "popstate" in js, "دکمهٔ برگشت گوشی وصل نشده"
    assert "/api/find-file" in js, "جست‌وجوی فایل در پنجرهٔ پیش‌نمایش نیست"


def test_files_root_fallback_and_guard() -> None:
    """سرور: فایل‌های ریشهٔ برنامه هم سرو شوند، ولی .env/data هرگز."""
    src = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    assert "roots = [WORKSPACE.resolve(), Path(__file__).resolve().parent]" in src, "فایل ریشهٔ برنامه سرو نمی‌شود"
    assert '"X-Frame-Options": "SAMEORIGIN"' in src, "iframe خودِ برنامه بلاک می‌شود"
    assert '"@app.get("/api/find-file")' not in src and '/api/find-file' in src, "مسیر جست‌وجو نیست"
    assert '".venv", "node_modules", ".arena", "logs"' in src, "نگهبان پوشه‌های خصوصی نیست"


def test_quick_mode() -> None:
    """حالت ⚡ سریع: مدل سبک‌تر + گام‌های کمتر، هم در سرور هم در رابط."""
    root = Path(__file__).resolve().parents[1]
    src = (root / "server.py").read_text(encoding="utf-8")
    cfg = (root / "mega" / "config.py").read_text(encoding="utf-8")
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    assert '@app.post("/api/quick")' in src, "مسیر حالت سریع نیست"
    assert "s.fast_mode = on" in src and 's.model_tier = "cheap"' in src
    assert "fast_mode: bool = False" in cfg, "فیلد fast_mode در تنظیمات نیست"
    for i in ("qFast", "qFull", "qMsg"):
        assert f'id="{i}"' in html, f"دکمهٔ {i} در تب مغز نیست"
    assert "setQuick" in html and "qSync" in html


def test_speed_rank() -> None:
    """حالت سریع: مدل سبک جلو می‌افتد، مدل‌های فکری عقب."""
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    from mega.providers import speed_rank
    assert speed_rank("@cf/meta/llama-4-scout") == 0
    assert speed_rank("llama-3.1-8b-instant") == 0
    assert speed_rank("gemini-2.0-flash") == 0
    assert speed_rank("@cf/nvidia/nemotron-3-120b-a12b") == 3      # فکری → کند
    assert speed_rank("deepseek-r1") == 3
    assert speed_rank("gpt-4.1") == 1
    assert speed_rank("") == 1


def test_fast_mode_picks_fast_model(monkeypatch=None) -> None:
    """در حالت سریع، resolve_role واقعاً مدل سبک را انتخاب می‌کند (نه مدل فکری)."""
    import asyncio, sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    from mega import providers as P
    from mega.config import Settings

    async def fake_pick(pid, prefs, exclude, how_many=3, tier="max"):
        return list(prefs)[:how_many]

    async def run():
        orig_pick = P._pick_from_provider
        P._pick_from_provider = fake_pick
        try:
            P.PROVIDERS["cloudflare"].key_override = "test-key"
            slow = Settings(); slow.fast_mode = False
            fast = Settings(); fast.fast_mode = True
            a = await P.resolve_role("judge", settings=slow)
            b = await P.resolve_role("judge", settings=fast)
            return a, b
        finally:
            P._pick_from_provider = orig_pick
            P.PROVIDERS["cloudflare"].key_override = None

    a, b = asyncio.run(run())
    assert a and b
    assert P.speed_rank(b.model) <= P.speed_rank(a.model), (a.model, b.model)
    assert P.is_reasoning(a.model) or P.speed_rank(b.model) == 0, (a.model, b.model)


def test_guide_has_groq_steps() -> None:
    """راهنما باید گام‌به‌گام Groq و OpenRouter را داشته باشد (کاربر موبایلی)."""
    g = (Path(__file__).resolve().parents[1] / "web" / "guide.html").read_text(encoding="utf-8")
    for need in ("console.groq.com/keys", "gsk_", "openrouter.ai/keys", "sk-or-",
                 "Create API Key", "۱۲۷.۰.۰.۱:۱۰۸۰۹" .replace("۱۲۷.۰.۰.۱:۱۰۸۰۹", "127.0.0.1:10809")):
        assert need in g, f"راهنما ناقص است: {need}"
    assert "۱ تریلیون" in g and "۶۷۱ میلیارد" in g


def test_groq_models_are_current() -> None:
    """مدل‌های Groq باید همان‌هایی باشند که با کلید واقعی تست شدند (اسم‌های مرده ممنوع)."""
    root = Path(__file__).resolve().parents[1]
    cfg = (root / "mega" / "config.py").read_text(encoding="utf-8")
    dead = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
            "moonshotai/kimi-k2-instruct"]
    for d in dead:
        assert d not in cfg, f"مدل بازنشستهٔ Groq برگشته: {d}"
    for live in ("openai/gpt-oss-120b", "groq/compound", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"):
        assert live in cfg, f"مدل تأییدشدهٔ Groq غایب است: {live}"


def test_big_free_550b_registered() -> None:
    """مغز ۵۵۰ میلیاردی رایگان باید در فهرست OpenRouter باشد (دلیل: درخواست کاربر)."""
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    from mega.config import PROVIDERS, ROLE_CANDIDATES
    orp = PROVIDERS["openrouter"].default_models
    assert any("nemotron-3-ultra-550b" in m for m in orp), "مدل ۵۵۰ میلیاردی رایگان نیست"
    joined = " ".join(m for _, ms in ROLE_CANDIDATES["expert"] for m in ms)
    assert "nemotron-3-ultra-550b" in joined or "nemotron-3-super-120b" in joined
    src = (_P(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    assert '"nemotron-3-ultra-550b": (550' in src, "اندازهٔ ۵۵۰ میلیارد در جدول مغز نیست"


def test_brain_label_picks_550b_for_openrouter() -> None:
    """نشان «مغز فعال» باید ۵۵۰ میلیارد را از نام مدل درست بخواند (بلندترین تطابق برنده)."""
    import os, sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    import server
    from mega.config import PROVIDERS
    for pid, p in PROVIDERS.items():
        os.environ.pop(p.env_key, None)
        p.key_override = None
    os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
    try:
        b = server._brain_label()
        assert b["params"] == 550, b
        assert "۵۵۰ میلیارد" in b["display"]
    finally:
        os.environ["OPENROUTER_API_KEY"] = ""


def test_selftest_tab() -> None:
    """تب «🧪 تست سیستم»: دکمه + مسیر /api/selftest + گروه‌های تست."""
    root = Path(__file__).resolve().parents[1]
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    src = (root / "server.py").read_text(encoding="utf-8")
    assert 'data-tab="test"' in html and 'id="tab-test"' in html, "تب تست نیست"
    assert "stRun" in html and "stRender" in html, "توابع تب تست نیست"
    assert '@app.get("/api/selftest")' in src, "مسیر /api/selftest نیست"
    for sec in ("سرور و سیستم", "بخش‌های برنامه", "سرویس‌های هوش", "دسترسی شبکه"):
        assert sec in src, f"گروه «{sec}» در تست نیست"
    for host in ("api.avalai.ir", "api.gapgpt.app", "api.groq.com", "openrouter.ai",
                 "open-meteo.com", "github.com"):
        assert host in src, f"آزمون دسترسی به {host} نیست"
    assert "proxy" in src and "🔀 پروکسی" in src, "آزمون پروکسی نیست"
