@echo off
chcp 65001 >nul
title MEGA-AI
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo پایتون پیدا نشد. از python.org نصبش کن و تیک "Add Python to PATH" را بزن.
  pause
  exit /b 1
)
python run_local.py %*
pause
