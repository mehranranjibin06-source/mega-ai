@echo off
chcp 65001 >nul 2>&1
title MehranAiShabestar - automatic startup + open the port
setlocal enabledelayedexpansion

rem ------- administrator rights (needed for firewall + scheduled task) -------
net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Asking for Administrator rights - please click YES in the window ...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo ============================================================
echo    MehranAiShabestar  -  one-time setup
echo    1^) open the ports in the Windows firewall
echo    2^) run the app automatically when Windows starts
echo    3^) restart it automatically if it ever crashes
echo ============================================================
echo.

rem ------- find the app folder -------
set "APPDIR="
for %%D in ("%~dp0." "%USERPROFILE%\mega-ai-main" "%USERPROFILE%\mega-ai" "C:\mega-ai-main" "C:\mega-ai") do (
  if exist "%%~D\start_vps.py" if not defined APPDIR set "APPDIR=%%~D"
)
if not defined APPDIR (
  echo   [!] start_vps.py was not found.
  echo       Put this file inside the mega-ai-main folder and run it again.
  echo.
  pause
  exit /b 1
)
echo   app folder : %APPDIR%

set "PY=python"
where python >nul 2>&1 || set "PY=py"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo   [!] Python 3 not found. Install it from python.org and tick Add-to-PATH.
  echo.
  pause
  exit /b 1
)

if not exist "%~dp0setup_autostart.ps1" (
  echo   [!] setup_autostart.ps1 must sit next to this file.
  echo.
  pause
  exit /b 1
)

echo.
echo   setting up the firewall, the startup task and the watchdog ...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_autostart.ps1" -AppDir "%APPDIR%"

echo.
echo   starting the app now ...
start "MehranAiShabestar" /min cmd /c ""%APPDIR%\run_server.bat""
timeout /t 8 /nobreak >nul

if exist "%APPDIR%\PORT.txt" (
  echo   the app is listening on:
  type "%APPDIR%\PORT.txt"
) else (
  echo   [i] PORT.txt is written the first time the app starts - check it in a moment.
)

echo.
echo ============================================================
echo    DONE.  On your phone open:   http://78.157.51.73:8000
echo.
echo    A minimized window named "MehranAiShabestar" is now
echo    running. KEEP IT OPEN - it is the server itself.
echo.
echo    Turn automatic startup OFF with:
echo        schtasks /delete /tn MehranAiShabestar /f
echo ============================================================
echo.
pause
