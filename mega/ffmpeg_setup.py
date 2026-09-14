# -*- coding: utf-8 -*-
"""نصب خودکار ffmpeg (بدون دسترسی ادمین) تا ساخت ویدیو/تیزر کار کند."""
from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = Path.home() / ".mega" / "ffmpeg"
URLS = [
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
]


def find() -> str:
    """مسیر ffmpeg اگر جایی هست، وگرنه رشتهٔ خالی."""
    w = shutil.which("ffmpeg")
    if w:
        return w
    d = os.environ.get("MEGA_FFMPEG_DIR")
    if d:
        p = Path(d) / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if p.exists():
            return str(p)
    if DEST.exists():
        hits = sorted(list(DEST.rglob("ffmpeg.exe")) + list(DEST.rglob("ffmpeg")))
        if hits:
            return str(hits[0])
    return ""


def _remember(bin_dir: str) -> None:
    try:
        env = ROOT / ".env"
        lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
        lines = [l for l in lines if not l.startswith("MEGA_FFMPEG_DIR=")]
        lines.append(f"MEGA_FFMPEG_DIR={bin_dir}")
        env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _download(url: str, out: Path, log) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as r, open(out, "wb") as f:
            shutil.copyfileobj(r, f, 1024 * 256)
        ok = out.stat().st_size > 1_000_000
        if not ok:
            log(f"[ffmpeg] file too small from {url}")
        return ok
    except Exception as e:  # noqa: BLE001
        log(f"[ffmpeg] download failed: {type(e).__name__}: {e}")
        return False


def ensure_ffmpeg(log=print) -> str:
    got = find()
    if got:
        log(f"[ffmpeg] ready: {got}")
        return got
    if os.name != "nt":
        return ""
    DEST.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.gettempdir()) / "ffmpeg-dl.zip"
    for url in URLS:
        log(f"[ffmpeg] downloading one time (~80 MB) from {url.split('/')[2]} ...")
        if not _download(url, tmp, log):
            continue
        try:
            with zipfile.ZipFile(tmp) as z:
                z.extractall(DEST)
        except Exception as e:  # noqa: BLE001
            log(f"[ffmpeg] unzip failed: {e}")
            continue
        hits = sorted(list(DEST.rglob("ffmpeg.exe")))
        if hits:
            bin_dir = str(hits[0].parent)
            os.environ["MEGA_FFMPEG_DIR"] = bin_dir
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
            _remember(bin_dir)
            log(f"[ffmpeg] installed: {hits[0]}")
            return str(hits[0])
    log("[ffmpeg] automatic install failed")
    return ""
