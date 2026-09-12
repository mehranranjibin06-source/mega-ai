# -*- coding: utf-8 -*-
"""برندینگ بصری: لوگو در پنل‌ها + فاوآیکون + مسیر /assets در سرور"""
from pathlib import Path

# ── ۱) مسیر /assets در سرور ─────────────────────────────────────────
srv = Path("server.py")
s = srv.read_text(encoding="utf-8")

route = '''

@app.get("/assets/{name}")
async def asset_file(name: str):
    """فایل‌های برند (لوگو، فونت) — از پوشه‌ی assets سرو می‌شوند."""
    from pathlib import Path as _P
    safe = _P(name).name                       # جلوگیری از پیمایش مسیر
    target = _P(__file__).resolve().parent / "assets" / safe
    if not target.is_file():
        return JSONResponse({"ok": False, "error": "فایل پیدا نشد"}, status_code=404)
    return FileResponse(target)

'''

anchor = '@app.get("/api/health")'
if '/assets/{name}' not in s:
    s = s.replace(anchor, route.lstrip("\n") + "\n" + anchor, 1)
    srv.write_text(s, encoding="utf-8")
    print("server.py: مسیر /assets اضافه شد")
else:
    print("server.py: مسیر /assets از قبل بود")

# ── ۲) پنل ساده: فاوآیکون + لوگو در هدر ─────────────────────────────
p = Path("web/simple.html")
h = p.read_text(encoding="utf-8")

if "logo_icon.png" not in h:
    h = h.replace(
        '<title>MehranAiShabestar — مهران‌هوش شبستر</title>',
        '<title>MehranAiShabestar — مهران‌هوش شبستر</title>\n'
        '<link rel="icon" type="image/png" href="/assets/favicon.png">\n'
        '<link rel="apple-touch-icon" href="/assets/favicon.png">',
        1)
    h = h.replace(
        '<div class="brand"><span class="dot"></span> دستیار من <span class="pill" id="brandPill">MEGA-AI</span></div>',
        '<div class="brand">'
        '<img src="/assets/logo_icon.png" alt="MehranAiShabestar" '
        'style="width:34px;height:34px;border-radius:9px;object-fit:cover;'
        'box-shadow:0 0 14px #22d3ee55;border:1px solid #26305a"> '
        'MehranAiShabestar <span class="pill" id="brandPill">هوش مصنوعی</span></div>',
        1)
    p.write_text(h, encoding="utf-8")
    print("simple.html: لوگو + فاوآیکون اضافه شد")
else:
    print("simple.html: از قبل برندگذاری شده")

# ── ۳) پنل حرفه‌ای: فاوآیکون + لوگو ──────────────────────────────────
q = Path("web/index.html")
a = q.read_text(encoding="utf-8")
if "logo_icon.png" not in a:
    a = a.replace(
        '<title>MehranAiShabestar — کارگزار مطلق اختصاصی</title>',
        '<title>MehranAiShabestar — کارگزار مطلق اختصاصی</title>\n'
        '<link rel="icon" type="image/png" href="/assets/favicon.png">\n'
        '<link rel="apple-touch-icon" href="/assets/favicon.png">',
        1)
    # لوگوی هدر (کلاس .logo)
    a = a.replace('<div class="logo">',
                  '<div class="logo">'
                  '<img src="/assets/logo_icon.png" alt="MehranAiShabestar" '
                  'style="width:30px;height:30px;border-radius:8px;object-fit:cover;'
                  'box-shadow:0 0 14px #7c5cff66;border:1px solid #26305a">', 1)
    q.write_text(a, encoding="utf-8")
    print("index.html: لوگو + فاوآیکون اضافه شد")
else:
    print("index.html: از قبل برندگذاری شده")
