"""مرتب‌کردن فایل‌های یک پوشه در زیرپوشه‌ها بر اساس پسوند (پیش‌فرض: فقط نمایش)."""
import shutil
import sys
from collections import Counter
from pathlib import Path

GROUPS = {"عکس": {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"},
          "سند": {".pdf", ".docx", ".doc", ".txt", ".rtf", ".xlsx", ".csv"},
          "ویدیو": {".mp4", ".mov", ".mkv", ".avi"},
          "صدا": {".mp3", ".wav", ".m4a", ".ogg"},
          "کد": {".py", ".js", ".ts", ".html", ".css", ".json", ".sh", ".sql"}}


def group_of(suffix: str) -> str:
    for name, exts in GROUPS.items():
        if suffix.lower() in exts:
            return name
    return "سایر"


def plan(root: str | Path) -> list[tuple[Path, Path]]:
    moves = []
    for p in sorted(Path(root).iterdir()):
        if p.is_file() and not p.name.startswith("."):
            moves.append((p, Path(root) / group_of(p.suffix) / p.name))
    return moves


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    apply = "--apply" in sys.argv
    moves = plan(root)
    print(f"{len(moves)} فایل بررسی شد | حالت: {'انتقال واقعی' if apply else 'فقط نمایش (برای اجرا: --apply)'}")
    for src, dest in moves:
        print(f"  {src.name}  →  {dest.relative_to(root)}")
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
    print(Counter(group_of(s.suffix) for s, _ in moves).most_common())
