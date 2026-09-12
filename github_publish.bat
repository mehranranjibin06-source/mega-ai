@echo off
REM  MEGA-AI -- publish this project to your GitHub repo (Windows). ASCII only.
chcp 65001 >nul
title MEGA-AI publish to GitHub
cd /d "%~dp0"

echo.
echo   ============================================
echo     Publish MEGA-AI to GitHub
echo   ============================================
echo.
echo   1) Create an EMPTY repo first:  https://github.com/new
echo      (name: mega-ai   -   no README, no .gitignore)
echo   2) Paste its URL below. Example:
echo      https://github.com/username/mega-ai.git
echo.
set /p REMOTE="Repository URL: "
if "%REMOTE%"=="" (echo   No URL given. & pause & exit /b 1)

set /p TOKEN="GitHub token (optional - press Enter to skip): "

where git >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [!] Git is not installed. Get it from https://git-scm.com/download/win
  pause & exit /b 1
)

if not exist .git (
  git init -q
  git branch -M main
)
git add -A
git -c user.email="mega-ai@local" -c user.name="MEGA-AI" commit -q -m "MEGA-AI update" 2>nul

for /f "tokens=*" %%c in ('git rev-parse --short HEAD') do echo   Current commit: %%c

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
  echo   [X] Push failed. Possible reasons:
  echo       - token required / invalid
  echo       - wrong repository URL
  echo       - internet or proxy problem
  pause & exit /b 1
)

if not "%TOKEN%"=="" git remote set-url origin "%REMOTE%"
echo.
echo   [OK] Done! Your repo: %REMOTE%
pause
