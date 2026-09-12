@echo off
cd /d "%~dp0"
echo This publishes the project to your GitHub repo.
echo Create an EMPTY repo first at https://github.com/new
echo.
set /p REMOTE="Repository URL: "
if "%REMOTE%"=="" (echo No URL given. & pause & exit /b 1)
git init -q 2>nul
git branch -M main 2>nul
git add -A
git -c user.email="mehran@local" -c user.name="MehranAiShabestar" commit -q -m "MehranAiShabestar" 2>nul
git remote remove origin 2>nul
git remote add origin "%REMOTE%"
git push -u origin main
pause
