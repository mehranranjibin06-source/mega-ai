@echo off
REM  MEGA-AI -- run on this computer (ASCII only). Persian UI comes from run_local.py
chcp 65001 >nul
cd /d "%~dp0"
title MEGA-AI

where python >nul 2>nul
if errorlevel 1 goto nopython

python run_local.py %*
echo.
pause
exit /b 0

:nopython
echo.
echo   [!] Python not found.
echo   Install "Python 3.11" or newer from https://www.python.org/downloads/
echo   IMPORTANT: on the first installer screen tick  "Add python.exe to PATH"
echo.
pause
exit /b 1
