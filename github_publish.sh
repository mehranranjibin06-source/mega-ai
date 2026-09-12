#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  انتشار روی گیت‌هاب — مک/لینوکس
#    ./github_publish.sh https://github.com/USER/mega-ai.git
#  اگر توکن داری (گزینه‌ی مطمئن‌تر برای حساب‌های خصوصی):
#    ./github_publish.sh https://github.com/USER/mega-ai.git TOKEN
#  توکن را از: github.com/settings/tokens  (دسترسی repo) بگیر.
# ─────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

REMOTE="${1:-}"
TOKEN="${2:-}"
BRANCH="main"

if [ -z "$REMOTE" ]; then
  echo "❓ آدرس مخزن گیت‌هاب را بده، مثلاً:"
  echo "   ./github_publish.sh https://github.com/username/mega-ai.git"
  exit 1
fi

# اگر توکن دادی، داخل آدرس بگذار (فقط همین اجرا، ذخیره نمی‌شود)
PUSH_URL="$REMOTE"
if [ -n "$TOKEN" ]; then
  case "$REMOTE" in
    https://github.com/*) PUSH_URL="https://x-access-token:${TOKEN}@github.com/${REMOTE#https://github.com/}" ;;
  esac
fi

echo "▸ آماده‌سازی مخزن محلی…"
if [ ! -d .git ]; then
  git init -q
  git branch -M "$BRANCH"
fi
git add -A
if git diff --cached --quiet; then echo "  چیزی برای کامیت نیست (همه چیز قبلاً ذخیره شده)."; else
  git -c user.email="${GIT_EMAIL:-mega-ai@local}" -c user.name="${GIT_NAME:-MEGA-AI}" \
      commit -q -m "${1:+}MEGA-AI: پنل آسان + آپلود و تحلیل فایل + اجراکننده محلی"
  echo "  ✅ کامیت ساخته شد."
fi

echo "▸ اتصال به گیت‌هاب…"
git remote remove origin 2>/dev/null || true
git remote add origin "$PUSH_URL"
echo "▸ فرستادن (push)…"
git push -u origin "$BRANCH"

# آدرس تمیز را دوباره ست کن تا توکن در .git/config بماند نشود
git remote set-url origin "$REMOTE"
echo
echo "✅ انجام شد. مخزن تو: ${REMOTE%.git}"
echo "   روی لپ‌تاپ دیگر فقط این را بزن:"
echo "     git clone $REMOTE && cd mega-ai && ./start.sh"
