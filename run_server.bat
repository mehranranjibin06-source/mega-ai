@echo off
chcp 65001 >nul 2>&1
title MehranAiShabestar - Server  (KEEP THIS WINDOW OPEN)
setlocal
cd /d "%~dp0"

if not exist "start_vps.py" (
  echo.
  echo   [!] start_vps.py was not found here.
  echo       Put this file inside the mega-ai-main folder and run it again.
  echo.
  pause
  exit /b 1
)

set "PY=python"
where python >nul 2>&1 || set "PY=py"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [!] Python 3 was not found. Install it from python.org
  echo       and tick "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo    MehranAiShabestar  -  starting the app
echo    folder : %CD%
echo    python : %PY%
echo.
echo    *** DO NOT CLOSE THIS WINDOW ***
echo    phone  : http://78.157.51.73:8000
echo    it also starts by itself every time Windows boots
echo ============================================================
echo.

if "%MEGA_WATCHDOG%"=="0" goto once

:loop
%PY% -u start_vps.py
set "RC=%ERRORLEVEL%"
echo.
echo ------------------------------------------------------------
echo   The app stopped  (exit code %RC%).
if "%RC%"=="0" (
  echo   This was a normal stop.
) else (
  echo   Something went wrong - the message above is the reason.
  echo   Send a photo of this window to the assistant.
)
echo   Restarting in 15 seconds ...   (close this window to stop)
echo ------------------------------------------------------------
timeout /t 15 /nobreak >nul
goto loop

:once
%PY% -u start_vps.py
echo.
echo   The app stopped. This window stays open so you can read the reason.
pause
