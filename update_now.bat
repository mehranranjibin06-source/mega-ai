@echo off
chcp 65001 >nul 2>&1
title MehranAiShabestar - Update
cd /d "%~dp0"
echo ============================================================
echo   MehranAiShabestar  -  Update + Restart
echo ============================================================
echo.
echo [1/3] downloading updater...
set "OK="

rem --- try curl first
for %%U in (
  "https://gh.llkk.cc/https://raw.githubusercontent.com/mehranranjibin06-source/mega-ai/main/update_self.py"
  "https://ghproxy.net/https://raw.githubusercontent.com/mehranranjibin06-source/mega-ai/main/update_self.py"
  "https://raw.githubusercontent.com/mehranranjibin06-source/mega-ai/main/update_self.py"
) do (
  if not defined OK (
    curl -L -s -o "_u.py" %%U >nul 2>&1
    if exist "_u.py" for %%S in ("_u.py") do if %%~zS GTR 2000 set "OK=1"
  )
)

rem --- fallback: PowerShell (always available on Windows)
if not defined OK (
  echo    trying PowerShell...
  powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; $u=@('https://cdn.jsdelivr.net/gh/mehranranjibin06-source/mega-ai@main/update_self.py','https://gh.llkk.cc/https://raw.githubusercontent.com/mehranranjibin06-source/mega-ai/main/update_self.py'); foreach($x in $u){ try{ iwr $x -OutFile '_u.py' -ErrorAction Stop }catch{}; if((Test-Path '_u.py') -and ((Get-Item '_u.py').Length -gt 2000)){ break } }"
  if exist "_u.py" for %%S in ("_u.py") do if %%~zS GTR 2000 set "OK=1"
)

if not defined OK (
  echo.
  echo   FAILED to download updater.
  echo   Turn VPN on, then run this file again.
  echo.
  pause
  exit /b 1
)

set "PY=python"
where python >nul 2>&1 || set "PY=py"

echo [2/3] installing latest version  (may take 1-3 minutes)...
%PY% "_u.py" --restart
set "RC=%ERRORLEVEL%"

echo.
echo [3/3] done.  Installed version:
findstr /C:"APP_VERSION" "mega\config.py" 2>nul
echo.
echo   Open on your phone:  http://78.157.51.73:8000
echo.
pause
exit /b %RC%
