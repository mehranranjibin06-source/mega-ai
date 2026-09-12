#!/usr/bin/env bash
# ابرهوش — اجرای محلی + گرفتن لینک عمومی (لینوکس / مک)
set -e
cd "$(dirname "$0")"
echo
echo "  ابرهوش — در حال اجرا… (این پنجره را باز بگذار)"
echo
exec python3 cloud_link.py
