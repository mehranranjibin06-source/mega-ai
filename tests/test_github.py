"""
تست اتصال گیت‌هاب — با یک گیت‌هاب تقلبی (tests/fake_github.py) که همان API واقعی را جواب می‌دهد.
پس مسیر کامل «ساخت مخزن → blob → tree → commit → ref» واقعاً اجرا و بررسی می‌شود.

اجرا:
    python tests/fake_github.py --port 8787 &
    GITHUB_API=http://127.0.0.1:8787 GITHUB_TOKEN=test-token-123 python -m pytest tests/test_github.py -v
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAKE = os.environ.get("GITHUB_API", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "test-token-123")
pytestmark = pytest.mark.skipif(not FAKE, reason="سرور گیت‌هاب تقلبی بالا نیست (GITHUB_API تنظیم نشده)")


def _client():
    from mega.github_tool import GitHub
    return GitHub(TOKEN, api=FAKE)


def _reset():
    httpx.post(f"{FAKE}/__debug/reset", timeout=10)


def _state():
    return httpx.get(f"{FAKE}/__debug/state", timeout=10).json()


@pytest.fixture(autouse=True)
def fresh():
    _reset()
    yield


def test_bad_token_and_missing_token():
    from mega.github_tool import GitHub, GitHubError
    with pytest.raises(GitHubError):
        GitHub("")                                     # بدون توکن
    gh = _client()
    gh.token = "wrong"
    with pytest.raises(GitHubError) as e:
        asyncio.run(gh.whoami())
    assert "توکن" in str(e.value)


def test_whoami_and_scopes():
    gh = _client()
    me = asyncio.run(gh.whoami())
    assert me["login"] == "tester"
    scopes = asyncio.run(gh.scopes())
    assert "repo" in scopes


def test_test_token_helper():
    from mega.github_tool import test_token
    ok = asyncio.run(test_token(TOKEN))
    assert ok["ok"] and ok["login"] == "tester" and ok["can_push"]
    bad = asyncio.run(test_token("nope"))
    assert bad["ok"] is False and "hint" in bad


def test_collect_files_filters_secrets(tmp_path):
    from mega.github_tool import collect_files
    (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=secret", encoding="utf-8")
    (tmp_path / "clip.mp4").write_bytes(b"0" * 10)          # ویدیوی کوچک: مجاز است
    (tmp_path / "huge.mp4").write_bytes(b"0" * 9_000_000)   # بزرگ‌تر از سقف: رد می‌شود
    (tmp_path / "notes.log").write_text("x", encoding="utf-8")
    (tmp_path / "archive.zip").write_bytes(b"PK\x03\x04")
    d = tmp_path / "node_modules"
    d.mkdir()
    (d / "junk.js").write_text("x", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret", encoding="utf-8")

    files, warns = collect_files(tmp_path)
    names = {str(rel) for _p, rel in files}
    assert names == {"main.py", "clip.mp4"}, f"فایل‌های سالم باید بمانند، اما: {names}"
    assert any("huge.mp4" in w for w in warns), "فایل بزرگ باید با هشدار رد شود"


def test_create_repo_and_push_folder(tmp_path):
    from mega.github_tool import GitHubError
    gh = _client()
    # پروژه‌ی کوچک نمونه
    (tmp_path / "app.py").write_text("print('سلام')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# پروژه‌ی تست\n", encoding="utf-8")
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "util.js").write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")

    logs: list[str] = []
    res = asyncio.run(gh.push_folder(tmp_path, "mega-test", private=True,
                                     message="اولین کامیت از MEGA-AI",
                                     description="تست خودکار", progress=logs.append))
    assert res["ok"] and res["files"] == 3, res
    assert res["created"] is True
    assert res["repo"] == "tester/mega-test"
    assert res["commit"]

    st = _state()
    assert "tester/mega-test" in st["files"]
    tree = st["files"]["tester/mega-test"]
    assert set(tree) == {"app.py", "README.md", "src/util.js"}, tree
    assert ".env" not in tree, "فایل کلید هرگز نباید فرستاده شود!"
    assert "سلام" in tree["app.py"]
    assert ".env" not in tree, "فایل کلید هرگز نباید فرستاده شود!"

    # خواندن همان فایل از «گیت‌هاب»
    got = asyncio.run(gh.get_file("mega-test", "src/util.js"))
    assert got["exists"] and "export const" in got["content"]

    # push دوم روی همان مخزن → کامیت جدید با base_tree
    (tmp_path / "app.py").write_text("print('نسخه‌ی دوم')\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("تازه", encoding="utf-8")
    res2 = asyncio.run(gh.push_folder(tmp_path, "mega-test", message="بروزرسانی"))
    assert res2["created"] is False
    assert res2["commit"] != res["commit"]
    tree2 = _state()["files"]["tester/mega-test"]
    assert "نسخه‌ی دوم" in tree2["app.py"]
    assert set(tree2) >= {"app.py", "README.md", "src/util.js", "new.txt"}
    assert set(tree2) == {"app.py", "README.md", "src/util.js", "new.txt"}


def test_put_file_and_issues():
    gh = _client()
    asyncio.run(gh.create_repo("issue-test", private=True))
    r = asyncio.run(gh.put_file("issue-test", "notes/idea.md", "# ایده\nمتن تست",
                                "افزودن یادداشت"))
    assert r["ok"] and r["commit"]
    got = asyncio.run(gh.get_file("issue-test", "notes/idea.md"))
    assert "متن تست" in got["content"]

    iss = asyncio.run(gh.create_issue("issue-test", "باگ نمونه", "توضیح باگ"))
    assert iss["number"] == 1
    items = asyncio.run(gh.list_issues("issue-test"))
    assert items and items[0]["title"] == "باگ نمونه"


def test_list_repos():
    gh = _client()
    asyncio.run(gh.create_repo("r1", private=True))
    asyncio.run(gh.create_repo("r2", private=False))
    repos = asyncio.run(gh.list_repos())
    names = {r["name"] for r in repos}
    assert {"r1", "r2"} <= names


def test_gitignore_is_respected(tmp_path):
    """مثل خود گیت: هرچه در .gitignore است فرستاده نمی‌شود."""
    from mega.github_tool import collect_files
    (tmp_path / ".gitignore").write_text("workspace/\ndata\n*.log\n.env\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("x", encoding="utf-8")
    for d in ("workspace", "data"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "secret.txt").write_text("خصوصی", encoding="utf-8")
    (tmp_path / "app.log").write_text("log", encoding="utf-8")
    files, _w = collect_files(tmp_path)
    names = {str(rel) for _p, rel in files}
    assert names == {"main.py", ".gitignore"}, names


def test_project_push_excludes_private_data():
    """فرستادن خودِ پروژه نباید شامل workspace/ یا data/ یا .env باشد."""
    from mega.github_tool import collect_files
    root = ROOT
    files, _w = collect_files(root, extra_ignore=["data", "workspace", "skills/installed-pip.txt"])
    names = {str(rel).replace(os.sep, "/") for _p, rel in files}
    assert "server.py" in names and "README.md" in names
    assert not any(n.startswith(("workspace/", "data/")) for n in names), names
    assert not any(n == ".env" or n.endswith("/.env") for n in names), names


def test_duplicate_repo_name_gives_persian_error():
    gh = _client()
    asyncio.run(gh.create_repo("dup", private=True))
    from mega.github_tool import GitHubError
    with pytest.raises(GitHubError) as e:
        asyncio.run(gh.create_repo("dup", private=True))
    assert "422" in str(e.value) or "قبلاً" in str(e.value)
