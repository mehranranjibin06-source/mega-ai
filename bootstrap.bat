@echo off
REM  MEGA-AI -- bootstrap (clone-or-update then run). ASCII only.
chcp 65001 >nul
title MEGA-AI bootstrap
setlocal
echo.
echo   ============================================
echo     MEGA-AI  -  install / update and run
echo   ============================================
echo.
set /p REPO="GitHub repository URL: "
if "%REPO%"=="" (echo   No URL given. & pause & exit /b 1)
set DEST=%USERPROFILE%\mega-ai

where git >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [!] Git is not installed.
  echo       Either install it from https://git-scm.com/download/win
  echo       or use GitHub "Code - Download ZIP", extract it and run start.bat
  pause & exit /b 1
)

if exist "%DEST%\.git" (
  echo   Updating existing copy ...
  cd /d "%DEST%" & git pull --ff-only
) else (
  echo   Downloading into %DEST% ...
  git clone "%REPO%" "%DEST%"
  cd /d "%DEST%"
)
echo   Starting ...
call start.bat
