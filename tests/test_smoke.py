"""تست دود: مطمئن می‌شود اجزای اصلی سالم ایمپورت و کار می‌کنند (بدون نیاز به کلید API)."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


def test_imports():
    import mega.agent  # noqa: F401
    import mega.analyze  # noqa: F401
    import mega.config  # noqa: F401
    import mega.media  # noqa: F401
    import mega.orchestrator  # noqa: F401
    import mega.providers  # noqa: F401
    import mega.vision  # noqa: F401


def test_providers_iran_first():
    from mega.config import PROVIDERS
    ids = list(PROVIDERS)
    assert ids[0] == "avalai", "گیت‌وی‌های ایرانی باید اول فهرست باشند"
    assert {"gapgpt", "metisai", "winkapi", "sinox", "jarvis"} <= set(ids)
    assert PROVIDERS["custom"].env_key == "CUSTOM_API_KEY"


def test_key_status_without_keys(monkeypatch):
    """کلید داخلی حالت نمایشی نباید به‌عنوان کلید واقعی کاربر شمرده شود."""
    from mega import demo_model
    from mega.config import PROVIDERS, key_status
    for name in ("OPENAI_API_KEY", "AVALAI_API_KEY", "CUSTOM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    p = PROVIDERS["openai"]
    old_override, old_active = p.key_override, demo_model.BRIDGE["active"]
    try:
        demo_model.BRIDGE["active"] = True
        p.key_override = "demo-mode"            # همان کاری که enable() می‌کند
        ks = key_status()
        assert ks["openai"]["configured"] is False, "کلید نمایشی «کلید واقعی» نیست"
        assert ks["openai"]["demo_bridge"] is True
    finally:
        p.key_override = old_override
        demo_model.BRIDGE["active"] = old_active


def test_analyze_csv(tmp_path):
    from mega.analyze import analyze_file
    csv = tmp_path / "s.csv"
    csv.write_text("name,qty,price\nقهوه,3,250000\nکیک,5,120000\nقهوه,2,250000\n", encoding="utf-8")
    res = asyncio.run(analyze_file(csv, use_model=False))
    assert res["ok"] and res["kind"] == "data"
    assert res["facts"]["rows"] == 3 and res["facts"]["columns"] == 3
    assert "قهوه" in json.dumps(res["facts"], ensure_ascii=False)


def test_analyze_python_syntax_error(tmp_path):
    from mega.analyze import analyze_file
    bad = tmp_path / "bad.py"
    bad.write_text("def f():\n    return 1\n", encoding="utf-8")
    ok = asyncio.run(analyze_file(bad, use_model=False))
    assert ok["ok"] and ok["kind"] == "code"
    assert "سالم" in ok["facts"]["syntax"]

    broken = tmp_path / "broken.py"
    broken.write_text("def f()\n    return 1\n", encoding="utf-8")
    res = asyncio.run(analyze_file(broken, use_model=False))
    assert "خطا" in res["facts"]["syntax"] and res["facts"]["syntax_error"]["line"] == 1


def test_poster_and_photo(tmp_path):
    from mega.media import make_image, poster_from_photo
    p = make_image(tmp_path / "poster.png", "کافه ماه", ["یک", "دو"],
                   theme="بنفش شب", ratio="9:16", subtitle="زیرنویس", caption="پایین")
    assert Path(p).is_file() and Path(p).stat().st_size > 5000
    q = poster_from_photo(p, tmp_path / "from_photo.png", title="از عکس", ratio="1:1")
    assert q["ok"] and Path(q["path"]).is_file()


def test_agent_tool_specs_exist():
    from mega.agent import AGENT_SPECS
    names = {t["name"] for t in AGENT_SPECS}
    assert {"finish", "make_ad", "make_video", "make_image", "poster_from_photo",
            "analyze_file", "tts", "stt"} <= names


def test_inception_prompts():
    from mega.config import WORKSPACE
    inc = WORKSPACE.parent / "inception"
    files = [f for f in inc.glob("*.md") if f.name.lower() != "readme.md"]
    assert len(files) >= 5, "پروژه‌های آماده باید موجود باشند"


def test_web_panels():
    from mega.config import WEB_DIR
    simple = (WEB_DIR / "simple.html").read_text(encoding="utf-8")
    assert "آپلود فایل" in simple and "انجامش بده" in simple
    assert (WEB_DIR / "index.html").is_file()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
