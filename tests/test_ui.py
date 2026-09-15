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
    assert "histOpen()" in nav, "دکمهٔ تاریخچه در نوار بالا نیست"
    assert "updOpen()" in nav, "دکمهٔ آپدیت در نوار بالا نیست"


def test_console_updater_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    s = (root / "update_self.py").read_text(encoding="utf-8")
    assert "updater.update" in s and "--restart" in s
