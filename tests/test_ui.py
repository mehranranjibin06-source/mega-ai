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
