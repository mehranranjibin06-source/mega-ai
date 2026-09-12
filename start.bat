@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto usepy
python run_local.py
goto end
:usepy
py run_local.py
:end
pause
