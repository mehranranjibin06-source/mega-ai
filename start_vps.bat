@echo off
REM  MEGA-AI -- Windows launcher (ASCII only: safe on every Windows codepage)
REM  All Persian messages are printed by start_vps.py (Python renders them correctly).
chcp 65001 >nul
cd /d "%~dp0"
title MehranAiShabestar

where python >nul 2>nul
if errorlevel 1 goto nopython

python start_vps.py
echo.
pause
exit /b 0

:nopython
echo.
echo   [!] Python not found on this server.
echo.
echo   Install "Python 3.11" (or newer) from:
echo       https://www.python.org/downloads/
echo.
echo   IMPORTANT: on the installer's first screen, tick
echo       "Add python.exe to PATH"
echo.
echo   Then double-click start_vps.bat again.
echo.
pause
exit /b 1
