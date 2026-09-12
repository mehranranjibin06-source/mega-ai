@echo off
chcp 65001 >nul
title انتشار MEGA-AI روی گیت‌هاب
cd /d "%~dp0"

echo ═══════════════════════════════════════════
echo   انتشار روی گیت‌هاب (ویندوز)
echo ═══════════════════════════════════════════
echo.
echo این اسکریپت پروژه را کامیت می‌کند و به مخزن تو می‌فرستد.
echo.
echo ۱) اول در مرورگر یک مخزن خالی بساز:  github.com/new
echo    (نام: mega-ai   ، بدون README/gitignore)
echo ۲) آدرس مخزن را همین‌جا بچسبان. مثال:
echo    https://github.com/username/mega-ai.git
echo.

set /p REMOTE="آدرس مخزن: "
if "%REMOTE%"=="" (echo آدرسی وارد نشد. & pause & exit /b 1)

set /p TOKEN="توکن گیت‌هاب (اختیاری — Enter برای رد کردن): "

where git >nul 2>nul
if errorlevel 1 (
  echo.
  echo گیت نصب نیست. از https://git-scm.com/download/win نصبش کن و دوباره اجرا کن.
  pause & exit /b 1
)

if not exist .git (
  git init -q
  git branch -M main
)
git add -A
git -c user.email="mega-ai@local" -c user.name="MEGA-AI" commit -q -m "MEGA-AI: پنل آسان + آپلود و تحلیل فایل + اجراکننده محلی" 2>nul

for /f "tokens=*" %%c in ('git rev-parse --short HEAD') do echo کامیت فعلی: %%c

if "%TOKEN%"=="" (
  git remote remove origin 2>nul
  git remote add origin "%REMOTE%"
) else (
  set PUSHURL=%REMOTE:https://github.com/%=https://x-access-token:%TOKEN%@github.com/%
  git remote remove origin 2>nul
  git remote add origin "%PUSHURL%"
)

git push -u origin main
if errorlevel 1 (
  echo.
  echo ❌ فرستادن نشد. چند احتمال:
  echo    • توکن لازم است (برای مخزن خصوصی یا وقتی رمز عبور قبول نشود)
  echo    • آدرس اشتباه است  •  اینترنت/پروکسی
  pause & exit /b 1
)

if not "%TOKEN%"=="" git remote set-url origin "%REMOTE%"
echo.
echo ✅ انجام شد! مخزن تو: %REMOTE%
pause
