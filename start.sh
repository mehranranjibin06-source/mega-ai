#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  MEGA-AI — اجرا روی مک/لینوکس (نصب خودکار + باز شدن مرورگر)
#    ./start.sh            اجرای ساده
#    ./start.sh --lan      در دسترس از گوشی/تبلت روی همان وای‌فای
#    ./start.sh --port 9000
# ─────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else
  echo "پایتون پیدا نشد. از python.org نصبش کن (۳.۱۰ یا بالاتر) و دوباره اجرا کن."; exit 1
fi

exec "$PY" run_local.py "$@"
