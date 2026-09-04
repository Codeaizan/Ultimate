@echo off
:: ─────────────────────────────────────────────────────────────────────────
:: run.bat
:: Launches TopMost Shield with administrator privileges.
:: ─────────────────────────────────────────────────────────────────────────

echo Starting TopMost Shield...

:: Check for admin - if not admin, relaunch elevated
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: Run the Python app
cd /d "%~dp0"
python app\main.py %*
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with an error.
    pause
)
