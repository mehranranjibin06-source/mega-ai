@echo off
REM  MEGA-AI -- run + get a public link for the phone (ASCII only).
REM  Persian messages come from cloud_link.py
chcp 65001 >nul
cd /d "%~dp0"
title MEGA-AI (cloud link)

where python >nul 2>nul
if errorlevel 1 goto nopython

python cloud_link.py
echo.
pause
exit /b 0

:nopython
echo.
echo   [!] Python not found.
echo   Install "Python 3.11" or newer from https://www.python.org/downloads/
echo   IMPORTANT: tick "Add python.exe to PATH" during setup.
echo.
pause
exit /b 1
