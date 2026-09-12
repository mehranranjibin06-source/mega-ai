#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  نصب از صفر روی یک کامپیوتر تازه (مک/لینوکس)
#    ./bootstrap.sh https://github.com/USER/mega-ai.git
#  یا اگر همین پوشه را داری، فقط: ./start.sh
# ─────────────────────────────────────────────────────────────────────
set -e
REPO="${1:-}"
DEST="${2:-$HOME/mega-ai}"
if [ -z "$REPO" ]; then
  echo "آدرس مخزن را بده: ./bootstrap.sh https://github.com/USER/mega-ai.git"; exit 1
fi
if command -v git >/dev/null 2>&1; then
  if [ -d "$DEST/.git" ]; then (cd "$DEST" && git pull --ff-only) ; else
    git clone "$REPO" "$DEST"
  fi
else
  echo "گیت نصب نیست؛ فایل ZIP را از گیت‌هاب دانلود و باز کن، بعد ./start.sh"; exit 1
fi
cd "$DEST"
exec ./start.sh
