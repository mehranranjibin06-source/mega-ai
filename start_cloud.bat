@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto usepy
python cloud_link.py
goto end
:usepy
py cloud_link.py
:end
pause
