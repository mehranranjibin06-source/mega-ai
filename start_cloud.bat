@echo off
REM ابرهوش — اجرای محلی + گرفتن لینک عمومی (ویندوز)
REM فقط روی این فایل دوبار کلیک کن.
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   ابرهوش - در حال اجرا... (پنجره را باز بگذار)
echo.
python cloud_link.py
echo.
echo   برنامه بسته شد. براي اجراي دوباره روي start_cloud.bat کليک کن.
pause
