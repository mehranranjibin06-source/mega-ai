@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto usepy
python start_vps.py
goto end
:usepy
py start_vps.py
:end
pause
