"""پشتیبان‌گیری خودکار — MehranAiShabestar v9.9
کلیدها (.env)، پایگاه تاریخچه (data/) و فایل‌های مهم را در یک زیپ ذخیره می‌کند.
پوشهٔ workspace (فایل‌های ساخته‌شده) فقط با full=True اضافه می‌شود.
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT / "backups"
FILES = [".env", "PORT.txt", "START-HERE.txt", ".env.example", "requirements.txt"]
DIRS = ["data"]
WORKSPACE = ROOT / "workspace"
KEEP = 10                      # چند پشتیبان نگه داشته شود
MAX_FILE = 300 * 1024 * 1024   # فایل بزرگ‌تر از این رد می‌شود


def _add_dir(zf: zipfile.ZipFile, base: Path, files: list[str]) -> int:
    n = 0
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        try:
            if f.stat().st_size > MAX_FILE:
                continue
        except OSError:
            continue
        zf.write(f, str(f.relative_to(ROOT)))
        files.append(str(f.relative_to(ROOT)))
        n += 1
    return n


def make_backup(full: bool = False, tag: str = "auto") -> dict:
    """یک زیپ پشتیبان می‌سازد و مسیرش را برمی‌گرداند."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"backup-{stamp}-{tag}.zip"
    target = BACKUP_DIR / name
    listed: list[str] = []
    n = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in FILES:
            f = ROOT / rel
            if f.is_file():
                zf.write(f, rel)
                listed.append(rel)
                n += 1
        for rel in DIRS:
            base = ROOT / rel
            if base.is_dir():
                n += _add_dir(zf, base, listed)
        if full and WORKSPACE.is_dir():
            n += _add_dir(zf, WORKSPACE, listed)
        meta = {"name": name, "when": time.strftime("%Y-%m-%d %H:%M:%S"),
                "ts": int(time.time()), "files": n, "full": full, "tag": tag,
                "note": "پشتیبان MehranAiShabestar — رمز و تاریخچه و تنظیمات"}
        zf.writestr("backup-info.json", json.dumps(meta, ensure_ascii=False, indent=1))
    prune()
    size = target.stat().st_size
    return {"ok": True, "name": name, "path": str(target), "bytes": size, "files": n,
            "when": meta["when"], "ts": meta["ts"], "full": full, "tag": tag}


def rows() -> list[dict]:
    """فهرست پشتیبان‌ها (تازه‌ترین اول)."""
    if not BACKUP_DIR.is_dir():
        return []
    out: list[dict] = []
    for f in sorted(BACKUP_DIR.glob("backup-*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        info = {"name": f.name, "bytes": f.stat().st_size,
                "when": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime)),
                "ts": int(f.stat().st_mtime), "files": 0, "tag": "?"}
        try:
            with zipfile.ZipFile(f) as zf:
                names = zf.namelist()
                info["files"] = len([x for x in names if x != "backup-info.json"])
                if "backup-info.json" in names:
                    info.update({k: v for k, v in json.loads(zf.read("backup-info.json")).items()
                                 if k in ("full", "tag", "when", "ts", "files")})
        except Exception:  # noqa: BLE001
            pass
        out.append(info)
    return out


def list_backups() -> list[dict]:
    return rows()


def last() -> dict | None:
    r = rows()
    return r[0] if r else None


def prune(keep: int = KEEP) -> int:
    """پشتیبان‌های قدیمی را پاک می‌کند (تازه‌ترین‌ها می‌مانند)."""
    r = rows()
    removed = 0
    for info in r[keep:]:
        try:
            (BACKUP_DIR / info["name"]).unlink()
            removed += 1
        except OSError:
            pass
    return removed


def due(hours: float = 24.0) -> bool:
    """آیا وقت پشتیبان تازه است؟"""
    if hours <= 0:
        return False
    last_row = last()
    if not last_row:
        return True
    return (time.time() - last_row["ts"]) >= hours * 3600
