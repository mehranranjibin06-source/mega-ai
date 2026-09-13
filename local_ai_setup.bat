@echo off
cd /d "%~dp0"
python local_ai_setup.py %*
if errorlevel 1 py local_ai_setup.py %*
pause
