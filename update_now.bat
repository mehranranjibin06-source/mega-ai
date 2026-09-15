@echo off
chcp 65001 >nul 2>&1
title MehranAiShabestar - Update
cd /d "%~dp0"
echo ============================================================
echo   MehranAiShabestar  -  Update + Restart
echo ============================================================
echo.

set "PY=python"
where python >nul 2>&1 || set "PY=py"

echo [1/3] downloading updater...
set "OK="
for %%U in (
  "https://cdn.jsdelivr.net/gh/mehranranjibin06-source/mega-ai@main/update_self.py"
  "https://gh.llkk.cc/https://raw.githubusercontent.com/mehranranjibin06-source/mega-ai/main/update_self.py"
  "https://ghproxy.net/https://raw.githubusercontent.com/mehranranjibin06-source/mega-ai/main/update_self.py"
  "https://raw.githubusercontent.com/mehranranjibin06-source/mega-ai/main/update_self.py"
) do (
  if not defined OK (
    echo    try: %%U
    curl -L -s -o "_u.py" %%U >nul 2>&1
    if exist "_u.py" (
      for %%S in ("_u.py") do if %%~zS GTR 2000 set "OK=1"
    )
  )
)

if not defined OK (
  echo.
  echo   FAILED to download updater.
  echo   Check internet / turn VPN on, then run this file again.
  echo.
  pause
  exit /b 1
)

echo [2/3] installing latest version...
%PY% "_u.py" --restart
set "RC=%ERRORLEVEL%"

echo.
echo [3/3] done.  Version file:
findstr /C:"APP_VERSION" "mega\config.py" 2>nul
echo.
echo   Now open in your phone:  http://78.157.51.73:8000
echo.
pause
exit /b %RC%
