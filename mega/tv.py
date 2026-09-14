# -*- coding: utf-8 -*-
"""📺 افزودنی تلویزیون — کانال‌های آزاد فارسی، آذربایجانی و ترکی (IPTV رایگان).

فهرست کانال‌ها از مخزن عمومی iptv-org گرفته و ۱۲ ساعت کش می‌شود.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "tv.json"
COUNTRIES = [("ir", "ایران"), ("az", "آذربایجان"), ("tr", "ترکیه")]
SOURCE = "https://iptv-org.github.io/iptv/countries/{cc}.m3u"
TTL = 12 * 3600


def _parse(text: str, cc: str) -> list[dict]:
    out: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF"):
            name = line.split(",", 1)[1].strip() if "," in line else ""
            logo = re.search(r'tvg-logo="([^"]*)"', line)
            grp = re.search(r'group-title="([^"]*)"', line)
            cur = {"name": name, "logo": logo.group(1) if logo else "",
                   "group": grp.group(1) if grp else "", "country": cc}
        elif line and not line.startswith("#") and cur:
            cur["url"] = line
            out.append(cur)
            cur = None
    return out


def load(force: bool = False) -> dict:
    """فهرست کانال‌ها (با کش ۱۲ ساعته)."""
    if not force and CACHE.exists() and (time.time() - CACHE.stat().st_mtime) < TTL:
        try:
            data = json.loads(CACHE.read_text(encoding="utf-8"))
            if data.get("items"):
                return data
        except Exception:  # noqa: BLE001
            pass

    items: list[dict] = []
    try:
        import httpx
        with httpx.Client(timeout=45, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (MegaAI TV)"}) as c:
            for cc, label in COUNTRIES:
                try:
                    r = c.get(SOURCE.format(cc=cc))
                    if r.status_code == 200:
                        rows = _parse(r.text, cc)
                        for row in rows:
                            row["country_label"] = label
                        items += rows
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        pass

    data = {"updated": time.time(), "items": items}
    if items:
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return data
