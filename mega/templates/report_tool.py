"""ابزار کوچک گزارش‌گیری: آمار فایل‌های یک پوشه + ساخت گزارش متنی فارسی."""
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


def stats(root: str | Path = ".") -> dict:
    root = Path(root)
    files = [p for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")]
    by_ext = Counter(p.suffix.lower() or "(بدون پسوند)" for p in files)
    size = sum(p.stat().st_size for p in files)
    biggest = sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:5]
    return {"root": str(root), "count": len(files), "size_mb": round(size / 1024 / 1024, 2),
            "by_ext": by_ext.most_common(8),
            "biggest": [(p.name, f"{p.stat().st_size / 1024:.0f}KB") for p in biggest]}


def write_report(data: dict, out: str | Path = "report.txt") -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"گزارش پوشه — {data['root']}", f"تاریخ: {stamp}",
             f"تعداد فایل: {data['count']} | حجم کل: {data['size_mb']} مگابایت", "", "بر اساس پسوند:"]
    lines += [f"  {ext}: {n}" for ext, n in data["by_ext"]]
    lines += ["", "بزرگ‌ترین فایل‌ها:"] + [f"  {n} ({s})" for n, s in data["biggest"]]
    Path(out).write_text("\n".join(lines), encoding="utf-8")
    return Path(out)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    data = stats(root)
    print(data)
    print("گزارش ساخته شد:", write_report(data))
