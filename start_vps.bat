@echo off
REM ════════════════════════════════════════════════════════════
REM   ابرهوش روی سرور ویندوزی خودت (کنار ربات معامله‌گر)
REM   - رمز می‌گذارد تا هرکسی که آی‌پی سرورت را دارد وارد نشود
REM   - پورت را برای دسترسی از بیرون باز می‌کند (فایروال ویندوز)
REM   - آدرس نهایی را نشان می‌دهد → همان را در گوشی باز کن
REM ════════════════════════════════════════════════════════════
chcp 65001 >nul
cd /d "%~dp0"
title ابرهوش (سرور)

echo.
echo  ==========================================================
echo     ابرهوش روی سرور خودت - نصب و اجرا
echo  ==========================================================
echo.

REM ── ۱) پایتون هست؟
where python >nul 2>nul
if errorlevel 1 (
  echo  [!] پایتون نصب نیست.
  echo.
  echo      1. این آدرس را در مرورگر سرور باز کن:
  echo         https://www.python.org/downloads/
  echo      2. نسخه‌ی Python 3.12 را دانلود و نصب کن.
  echo      3. در صفحه‌ی نصب، تیک  "Add python.exe to PATH"  را بزن.
  echo      4. بعد دوباره روی همین فایل دوبار کلیک کن.
  echo.
  pause
  exit /b 1
)

REM ── ۱.۵) نمایش نسخه‌ی پایتون (باید ۳.۱۰ یا بالاتر باشد)
echo  [i] نسخه‌ی پایتون:
python -c "import sys; v=sys.version_info; print('       ', sys.version.split()[0], '(خوب است)' if v>=(3,10) else '(قدیمی! نسخه ۳.۱۰ یا بالاتر لازم است)')"
echo.

REM ── ۲) رمز (بار اول از تو می‌پرسد و ذخیره می‌کند)
if exist .env (
  findstr /b /c:"MEGA_PASSWORD=" .env >nul 2>nul
  if not errorlevel 1 goto havepass
)
echo  یک رمز برای برنامه انتخاب کن (فقط خودت بدانی).
echo  این رمز جلوی دسترسی غریبه‌ها به برنامه روی سرورت را می‌گیرد.
echo.
set /p NEWPASS="  رمز دلخواه: "
if "%NEWPASS%"=="" (
  echo  [!] رمز خالی بود. دوباره اجرا کن و یک رمز بزن.
  pause
  exit /b 1
)
echo MEGA_PASSWORD=%NEWPASS%>> .env

:havepass

REM ── ۳) پورت ۸۰۰۰ روی فایروال باز شود (اگر قبلاً باز نبوده)
netsh advfirewall firewall show rule name="MEGA-AI 8000" >nul 2>nul
if errorlevel 1 (
  echo  [i] باز کردن پورت 8000 در فایروال ویندوز ...
  netsh advfirewall firewall add rule name="MEGA-AI 8000" dir=in action=allow protocol=TCP localport=8000 >nul 2>nul
)

REM ── ۴) اجرا (بار اول کتابخانه‌ها را نصب می‌کند: چند دقیقه)
echo.
echo  [i] بار اول چند دقیقه طول می‌کشد (نصب کتابخانه‌ها). صبر کن ...
echo.
python run_local.py --lan --port 8000

echo.
echo  برنامه بسته شد. برای اجرای دوباره روی همین فایل کلیک کن.
pause
