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
where %PY% >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [!] Python was not found. Install Python 3 from python.org
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
echo    When you read  "the app is running"  open on your phone:
echo        http://78.157.51.73:8000
echo ============================================================
echo.

%PY% -u start_vps.py

echo.
echo ------------------------------------------------------------------
echo   The app stopped. The message above shows the reason.
echo   Take a photo of this window and send it to the assistant.
echo ------------------------------------------------------------------
pause
