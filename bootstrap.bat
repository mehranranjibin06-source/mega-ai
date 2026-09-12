@echo off
chcp 65001 >nul
title نصب و اجرای MEGA-AI
setlocal
echo ═══════════════════════════════════════════
echo   نصب و اجرای MEGA-AI روی این کامپیوتر
echo ═══════════════════════════════════════════
echo.
set /p REPO="آدرس مخزن گیت‌هاب: "
if "%REPO%"=="" (echo آدرسی وارد نشد. & pause & exit /b 1)
set DEST=%USERPROFILE%\mega-ai

where git >nul 2>nul
if errorlevel 1 (
  echo.
  echo گیت نصب نیست — یا از https://git-scm.com/download/win نصب کن،
  echo یا در گیت‌هاب دکمه‌ی «Code → Download ZIP» را بزن و فایل را باز کن و start.bat را اجرا کن.
  pause & exit /b 1
)

if exist "%DEST%\.git" (
  echo ▸ به‌روزرسانی نسخه‌ی موجود…
  cd /d "%DEST%" & git pull --ff-only
) else (
  echo ▸ دانلود پروژه در %DEST% …
  git clone "%REPO%" "%DEST%"
  cd /d "%DEST%"
)
echo ▸ اجرا…
call start.bat
