# -*- coding: utf-8 -*-
"""✨ افزودنی‌های رایگان و بدون کلید.

۱) 🌦 آب‌وهوا  — Open-Meteo (بدون کلید، بدون ثبت‌نام)
۲) 📻 رادیو    — radio-browser.info (بدون کلید)
۳) 📰 اخبار    — خوراک‌های RSS فارسی (بدون کلید)
۴) 🌐 مترجم    — MyMemory (بدون کلید)

هیچ‌کدام به API key نیاز ندارند؛ فقط اینترنت می‌خواهند.
"""
from __future__ import annotations

import concurrent.futures as _fut
import html as _html
import json
import re
import time
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (MehranAiShabestar Addons)"}


def _client(**kw):
    import httpx
    kw.setdefault("timeout", 25)
    kw.setdefault("follow_redirects", True)
    kw.setdefault("headers", UA)
    return httpx.Client(**kw)


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def _read_cache(name: str, ttl: float):
    p = _cache_path(name)
    try:
        if p.exists() and (time.time() - p.stat().st_mtime) < ttl:
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return None


def _write_cache(name: str, data: dict) -> None:
    try:
        _cache_path(name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


# ═══════════════════════ ۱) آب‌وهوا ═══════════════════════
WMO = {
    0: ("آسمان صاف", "☀️"), 1: ("اغلب صاف", "🌤"), 2: ("نیمه‌ابری", "⛅"), 3: ("ابری", "☁️"),
    45: ("مه", "🌫"), 48: ("مه یخ‌زده", "🌫"),
    51: ("نم‌نم باران", "🌦"), 53: ("باران سبک", "🌦"), 55: ("باران", "🌧"),
    56: ("باران یخ‌زده", "🌧"), 57: ("باران یخ‌زده", "🌧"),
    61: ("باران کم", "🌧"), 63: ("باران", "🌧"), 65: ("باران شدید", "🌧"),
    66: ("باران یخ‌زده", "🌧"), 67: ("باران یخ‌زده", "🌧"),
    71: ("برف کم", "🌨"), 73: ("برف", "🌨"), 75: ("برف شدید", "❄️"), 77: ("دانه‌های برف", "🌨"),
    80: ("رگبار", "🌦"), 81: ("رگبار", "🌧"), 82: ("رگبار شدید", "⛈"),
    85: ("برف رگباری", "🌨"), 86: ("برف رگباری", "❄️"),
    95: ("رعدوبرق", "⛈"), 96: ("رعدوبرق با تگرگ", "⛈"), 99: ("رعدوبرق شدید", "⛈"),
}
_FA_DAYS = {"Monday": "دوشنبه", "Tuesday": "سه‌شنبه", "Wednesday": "چهارشنبه",
            "Thursday": "پنجشنبه", "Friday": "جمعه", "Saturday": "شنبه", "Sunday": "یکشنبه"}


def _wk(iso: str) -> str:
    try:
        return _FA_DAYS.get(date.fromisoformat(iso).strftime("%A"), iso)
    except Exception:  # noqa: BLE001
        return iso


def weather(city: str = "تبریز") -> dict:
    """آب‌وهوای امروز + ۵ روز آیندهٔ هر شهری در دنیا (فارسی)."""
    city = (city or "تبریز").strip() or "تبریز"
    try:
        with _client() as c:
            g = c.get("https://geocoding-api.open-meteo.com/v1/search",
                      params={"name": city, "count": 1, "language": "fa", "format": "json"})
            places = (g.json() or {}).get("results") or []
            if not places:
                return {"ok": False, "error": f"شهر «{city}» پیدا نشد — املای انگلیسی/فارسی را امتحان کن"}
            p = places[0]
            f = c.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": p["latitude"], "longitude": p["longitude"],
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m,weather_code",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "timezone": "auto", "forecast_days": 5,
            })
            d = f.json() or {}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"اتصال به سرویس هوا ممکن نشد: {e}"}

    cur = d.get("current") or {}
    code = int(cur.get("weather_code") or 0)
    desc, icon = WMO.get(code, ("نامشخص", "🌡"))
    daily = d.get("daily") or {}
    days = []
    for i, ds in enumerate(daily.get("time") or []):
        dc = int((daily.get("weather_code") or [0])[i] or 0)
        dd, di = WMO.get(dc, ("نامشخص", "🌡"))
        days.append({
            "date": ds, "day": "امروز" if i == 0 else _wk(ds),
            "max": round((daily.get("temperature_2m_max") or [0])[i]),
            "min": round((daily.get("temperature_2m_min") or [0])[i]),
            "desc": dd, "icon": di,
        })
    return {
        "ok": True, "city": p.get("name") or city, "country": p.get("country") or "",
        "region": p.get("admin1") or "", "timezone": d.get("timezone") or "",
        "current": {"temp": round(cur.get("temperature_2m") or 0),
                    "feels": round(cur.get("apparent_temperature") or 0),
                    "humidity": round(cur.get("relative_humidity_2m") or 0),
                    "wind": round(cur.get("wind_speed_10m") or 0),
                    "desc": desc, "icon": icon},
        "days": days, "updated": time.time(),
    }


# ═══════════════════════ ۲) رادیو ═══════════════════════
RADIO_HOSTS = ["de1.api.radio-browser.info", "nl1.api.radio-browser.info",
               "at1.api.radio-browser.info", "fi1.api.radio-browser.info"]
RADIO_COUNTRIES = [("IR", "ایران"), ("AZ", "آذربایجان"), ("TR", "ترکیه"), ("AF", "افغانستان"), ("TJ", "تاجیکستان")]
RADIO_TTL = 6 * 3600


def radio(country: str = "", q: str = "", force: bool = False) -> dict:
    """ایستگاه‌های رادیوی اینترنتی رایگان (پیش‌فرض: کشورهای فارسی/ترکی‌زبان)."""
    country = (country or "").upper().strip()
    q = (q or "").strip()
    cname = "all"
    if not q:
        cname = country or "all"
    key = f"radio-{cname}.json"
    if not force and not q:
        hit = _read_cache(key, RADIO_TTL)
        if hit and hit.get("items"):
            return hit

    items: list[dict] = []
    last_err = ""
    codes = [country] if country else [cc for cc, _ in RADIO_COUNTRIES]
    for cc in codes:
        got: list[dict] = []
        for host in RADIO_HOSTS:
            try:
                with _client(timeout=20) as c:
                    params = {"countrycode": cc, "hidebroken": "true", "order": "clickcount",
                              "reverse": "true", "limit": "250"}
                    if q:
                        params = {"name": q, "hidebroken": "true", "order": "clickcount",
                                  "reverse": "true", "limit": "120"}
                    r = c.get(f"https://{host}/json/stations/search", params=params)
                    if r.status_code != 200:
                        last_err = f"{host} → {r.status_code}"
                        continue
                    rows = r.json() or []
                label = dict(RADIO_COUNTRIES).get(cc, cc)
                for s in rows:
                    url = (s.get("url_resolved") or s.get("url") or "").strip()
                    if not url:
                        continue
                    got.append({
                        "name": (s.get("name") or "بی‌نام").strip(),
                        "url": url, "logo": (s.get("favicon") or "").strip(),
                        "country": cc, "country_label": label,
                        "tags": [t for t in (s.get("tags") or "").split(",") if t][:4],
                        "codec": (s.get("codec") or "").upper(),
                        "bitrate": s.get("bitrate") or 0,
                        "votes": s.get("votes") or 0,
                        "homepage": (s.get("homepage") or "").strip(),
                    })
                break
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
        items += got
        if q:
            break
    items.sort(key=lambda x: -(x.get("votes") or 0))
    out = {"ok": bool(items), "count": len(items), "items": items[:600],
           "updated": time.time(), "error": "" if items else (last_err or "ایستگاهی پیدا نشد")}
    if not q and items:
        _write_cache(key, out)
    return out


# ═══════════════════════ ۳) اخبار ═══════════════════════
FEEDS = [
    ("ایسنا", "https://www.isna.ir/rss"),
    ("ایرنا", "https://www.irna.ir/rss"),
    ("خبرگزاری مهر", "https://www.mehrnews.com/rss"),
    ("فارس", "https://www.farsnews.ir/rss"),
    ("تابناک", "https://www.tabnak.ir/fa/rss/allnews"),
    ("خبرآنلاین", "https://www.khabaronline.ir/rss"),
    ("بی‌بی‌سی فارسی", "https://feeds.bbci.co.uk/persian/rss.xml"),
    ("یورونیوز فارسی", "https://parsi.euronews.com/rss"),
    ("دویچه‌وله فارسی", "https://rss.dw.com/xml/rss-fa-all"),
]
NEWS_TTL = 20 * 60


def _strip_tags(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s or "", flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_rss(text: str, source: str) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(r"<(item|entry)\b.*?</\1>", text, re.S | re.I):
        block = m.group(0)
        t = re.search(r"<title[^>]*>(.*?)</title>", block, re.S | re.I)
        title = _strip_tags(t.group(1)) if t else ""
        lk = re.search(r"<link[^>]*>(.*?)</link>", block, re.S | re.I)
        link = _strip_tags(lk.group(1)) if lk else ""
        if not link:
            lk2 = re.search(r'<link[^>]*href="([^"]+)"', block, re.I)
            link = lk2.group(1) if lk2 else ""
        dt = re.search(r"<(pubDate|published|updated|dc:date)[^>]*>(.*?)</\1>", block, re.S | re.I)
        ts = 0.0
        raw_date = _strip_tags(dt.group(2)) if dt else ""
        if raw_date:
            try:
                ts = parsedate_to_datetime(raw_date).timestamp()
            except Exception:  # noqa: BLE001
                try:
                    ts = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).timestamp()
                except Exception:  # noqa: BLE001
                    ts = 0.0
        ds = re.search(r"<(description|summary)[^>]*>(.*?)</\1>", block, re.S | re.I)
        summary = _strip_tags(ds.group(2))[:260] if ds else ""
        if title and link:
            out.append({"title": title, "url": link, "source": source,
                        "ts": ts, "summary": summary})
    return out[:8]


def news(force: bool = False) -> dict:
    """تیترهای تازه از خبرگزاری‌های فارسی (هر منبعی که در دسترس باشد)."""
    if not force:
        hit = _read_cache("news.json", NEWS_TTL)
        if hit and hit.get("items"):
            return hit

    items: list[dict] = []
    status: list[dict] = []
    with _fut.ThreadPoolExecutor(max_workers=9) as ex:
        futs = {}
        for name, url in FEEDS:
            futs[ex.submit(_fetch_feed, url, name)] = name
        for fu in _fut.as_completed(futs):
            name = futs[fu]
            try:
                rows, err = fu.result()
            except Exception as e:  # noqa: BLE001
                rows, err = [], str(e)
            status.append({"source": name, "ok": rows and not err, "count": len(rows),
                           "error": err or ""})
            items += rows

    seen: set[str] = set()
    uniq: list[dict] = []
    for it in sorted(items, key=lambda x: -(x.get("ts") or 0)):
        k = it["title"][:70]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    ok_sources = [s["source"] for s in status if s["ok"]]
    out = {"ok": bool(uniq), "count": len(uniq), "items": uniq[:120],
           "sources": status, "sources_ok": ok_sources, "updated": time.time(),
           "error": "" if uniq else "هیچ منبع خبری در دسترس نبود (اینترنت/فیلتر را بررسی کن)"}
    if uniq:
        _write_cache("news.json", out)
    return out


def _fetch_feed(url: str, name: str) -> tuple[list[dict], str]:
    try:
        with _client(timeout=18) as c:
            r = c.get(url)
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        return _parse_rss(r.text, name), ""
    except Exception as e:  # noqa: BLE001
        return [], type(e).__name__


# ═══════════════════════ ۴) مترجم ═══════════════════════
LANGS = [("fa", "فارسی"), ("en", "انگلیسی"), ("ar", "عربی"), ("tr", "ترکی"),
         ("az", "آذربایجانی"), ("ru", "روسی"), ("de", "آلمانی"), ("fr", "فرانسوی"),
         ("es", "اسپانیایی"), ("zh-CN", "چینی"), ("hi", "هندی"), ("ku", "کردی")]


def _chunks(text: str, size: int = 450) -> list[str]:
    parts, cur = [], ""
    for piece in re.split(r"(?<=[.!؟?\n])\s+", text):
        if len(cur) + len(piece) + 1 > size and cur:
            parts.append(cur)
            cur = piece
        else:
            cur = (cur + " " + piece).strip()
    if cur:
        parts.append(cur)
    return parts or [text[:size]]


def translate(text: str, to: str = "en", frm: str = "fa") -> dict:
    """ترجمهٔ متن (بدون کلید، با سرویس رایگان MyMemory)."""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "متنی برای ترجمه ننوشتی"}
    to = (to or "en").strip()
    frm = (frm or "fa").strip()
    if frm == "auto":
        frm = "fa"
    outs: list[str] = []
    try:
        with _client(timeout=30) as c:
            for ch in _chunks(text):
                r = c.get("https://api.mymemory.translated.net/get",
                          params={"q": ch, "langpair": f"{frm}|{to}"})
                d = r.json() or {}
                out = ((d.get("responseData") or {}).get("translatedText") or "").strip()
                if not out or "MYMEMORY WARNING" in out.upper():
                    return {"ok": False, "error": "سرویس ترجمه الان جواب نداد — چند لحظه بعد امتحان کن"}
                outs.append(_html.unescape(out))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"اتصال به سرویس ترجمه ممکن نشد: {e}"}
    return {"ok": True, "text": " ".join(outs), "from": frm, "to": to,
            "chars": len(text), "engine": "MyMemory (رایگان)"}


def status() -> dict:
    """وضعیت سبک افزودنی‌ها برای داشبورد."""
    return {
        "ok": True,
        "addons": [
            {"id": "weather", "name": "آب‌وهوا", "icon": "🌦", "key": False, "url": "/more#weather"},
            {"id": "radio", "name": "رادیو اینترنتی", "icon": "📻", "key": False, "url": "/more#radio"},
            {"id": "news", "name": "اخبار فارسی", "icon": "📰", "key": False, "url": "/more#news"},
            {"id": "translate", "name": "مترجم", "icon": "🌐", "key": False, "url": "/more#translate"},
            {"id": "tv", "name": "تلویزیون", "icon": "📺", "key": False, "url": "/tv"},
        ],
    }
