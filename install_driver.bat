@echo off
:: ─────────────────────────────────────────────────────────────────────────
:: install_driver.bat
:: Installs and starts the TopMost Shield kernel driver.
:: Must be run as Administrator.
:: ─────────────────────────────────────────────────────────────────────────

echo ========================================================
echo   TopMost Shield - Kernel Driver Installer
echo ========================================================
echo.

:: Check for admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] This script must be run as Administrator.
    echo         Right-click and select "Run as administrator"
    pause
    exit /b 1
)

:: Check test signing
echo [1/4] Checking test signing mode...
bcdedit /enum {current} | findstr /i "testsigning.*Yes" >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Test signing is NOT enabled.
    echo.
    set /p ENABLE_TS="Enable test signing? This requires a reboot. (y/n): "
    if /i "%ENABLE_TS%"=="y" (
        bcdedit /set testsigning on
        echo [INFO] Test signing enabled. Please REBOOT and run this script again.
        pause
        exit /b 0
    ) else (
        echo [WARN] Driver may fail to load without test signing.
    )
) else (
    echo [OK] Test signing is enabled.
)
echo.

:: Check if driver file exists
echo [2/4] Locating driver binary...
set DRIVER_PATH=%~dp0driver\topmost_driver.sys
if not exist "%DRIVER_PATH%" (
    echo [ERROR] Driver file not found: %DRIVER_PATH%
    echo         Build the driver first using Visual Studio + WDK.
    echo.
    echo         Steps:
    echo         1. Open Visual Studio 2022
    echo         2. Create a new "Kernel Mode Driver (KMDF)" project
    echo         3. Replace the source with driver\topmost_driver.c
    echo         4. Build in Release x64 configuration
    echo         5. Copy the .sys file to driver\topmost_driver.sys
    pause
    exit /b 1
)
echo [OK] Found: %DRIVER_PATH%
echo.

:: Install the service
echo [3/4] Installing driver service...
sc query TopMostDriver >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Service already exists. Stopping and removing...
    sc stop TopMostDriver >nul 2>&1
    timeout /t 2 /nobreak >nul
    sc delete TopMostDriver >nul 2>&1
    timeout /t 2 /nobreak >nul
)

sc create TopMostDriver type= kernel start= demand binPath= "%DRIVER_PATH%" DisplayName= "TopMost Shield Kernel Driver"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create service.
    pause
    exit /b 1
)
echo [OK] Service created.
echo.

:: Start the driver
echo [4/4] Starting driver...
sc start TopMostDriver
if %errorlevel% neq 0 (
    echo [ERROR] Failed to start driver.
    echo         Make sure test signing is enabled and you've rebooted.
    pause
    exit /b 1
)
echo [OK] Driver started successfully!
echo.

:: Verify
echo ─────────────────────────────────────────────────────
sc query TopMostDriver
echo ─────────────────────────────────────────────────────
echo.
echo Driver is running! You can now launch the application:
echo   python app\main.py
echo.
pause
