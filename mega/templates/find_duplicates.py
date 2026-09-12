"""پیدا کردن فایل‌های تکراری یک پوشه با هش محتوا (بدون حذف خودکار)."""
import hashlib
import sys
from collections import defaultdict
from pathlib import Path


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def find_duplicates(root: str | Path = ".") -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            try:
                groups[file_hash(p)].append(p)
            except OSError:
                continue
    return {k: v for k, v in groups.items() if len(v) > 1}


def report(groups: dict[str, list[Path]]) -> int:
    total_waste = 0
    for i, (_h, files) in enumerate(groups.items(), 1):
        size = files[0].stat().st_size
        total_waste += size * (len(files) - 1)
        print(f"[{i}] {len(files)} نسخه‌ی یکسان ({size:,} بایت هرکدام):")
        for f in files:
            print(f"     - {f}")
    extra = sum(len(v) - 1 for v in groups.values())
    print()
    print(f"جمع نسخه‌های اضافی: {extra} | حجم قابل آزادسازی: {total_waste / 1024 / 1024:.2f} مگابایت")
    return total_waste


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    dupes = find_duplicates(root)
    print(f"پوشه‌ی بررسی‌شده: {Path(root).resolve()}")
    if not dupes:
        print("هیچ فایل تکراری پیدا نشد ✅")
    report(dupes)
