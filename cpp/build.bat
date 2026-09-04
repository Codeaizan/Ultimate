@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   TopMost Shield — C++ Build System
echo ============================================================
echo.

:: ─── Find MSVC ─────────────────────────────────────────────────
set "VCVARS="

:: Try VS 2022 BuildTools
if exist "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" (
    set "VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
)
:: Try VS 2022 Community
if "%VCVARS%"=="" if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" (
    set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"
)
:: Try VS 2022 Professional
if "%VCVARS%"=="" if exist "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat" (
    set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat"
)

if "%VCVARS%"=="" (
    echo [ERROR] MSVC not found! Install Visual Studio Build Tools.
    exit /b 1
)

echo [OK] Found MSVC: %VCVARS%
call "%VCVARS%" x64 >nul 2>&1

:: ─── Download NuGet ─────────────────────────────────────────────
cd /d "%~dp0"

if not exist "tools\nuget.exe" (
    echo [..] Downloading NuGet...
    mkdir tools 2>nul
    powershell -Command "Invoke-WebRequest -Uri 'https://dist.nuget.org/win-x86-commandline/latest/nuget.exe' -OutFile 'tools\nuget.exe'" 2>nul
    if errorlevel 1 (
        echo [ERROR] Failed to download NuGet
        exit /b 1
    )
    echo [OK] NuGet downloaded
)

:: ─── Download WebView2 SDK ──────────────────────────────────────
if not exist "packages" (
    echo [..] Installing WebView2 SDK...
    tools\nuget install Microsoft.Web.WebView2 -OutputDirectory packages -NonInteractive >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to install WebView2 SDK
        exit /b 1
    )
    echo [OK] WebView2 SDK installed
) else (
    echo [OK] WebView2 SDK already present
)

:: ─── Find WebView2 paths ────────────────────────────────────────
set "WV2_INC="
set "WV2_LIB="
set "WV2_DLL="

for /d %%d in (packages\Microsoft.Web.WebView2.*) do (
    set "WV2_INC=%%d\build\native\include"
    set "WV2_LIB=%%d\build\native\x64"
    set "WV2_DLL=%%d\runtimes\win-x64\native"
)

if "%WV2_INC%"=="" (
    echo [ERROR] WebView2 SDK not found in packages/
    exit /b 1
)

echo [OK] WebView2 Include: %WV2_INC%

:: ─── Compile ────────────────────────────────────────────────────
echo.
echo [..] Compiling...

mkdir bin 2>nul

cl.exe /nologo /EHsc /std:c++17 /O2 /DNDEBUG /DUNICODE /D_UNICODE ^
    /I"%WV2_INC%" ^
    src\main.cpp ^
    /Fe"bin\Acer.exe" ^
    /link /SUBSYSTEM:WINDOWS ^
    user32.lib shell32.lib ole32.lib oleaut32.lib shlwapi.lib version.lib ^
    "%WV2_LIB%\WebView2LoaderStatic.lib" ^
    /MACHINE:X64

if errorlevel 1 (
    echo.
    echo [ERROR] Compilation failed!
    exit /b 1
)

:: ─── Copy WebView2Loader.dll (fallback, not needed with static lib) ──
:: copy /Y "%WV2_DLL%\WebView2Loader.dll" bin\ >nul 2>&1

echo.
echo ============================================================
echo   [OK] Build successful!
echo   Output: %~dp0bin\Acer.exe
echo ============================================================
echo.
echo   Features:
echo     - WebView2 browser (ChatGPT, Gemini, Claude)
echo     - Always-on-top with kernel driver enforcement
echo     - Screen capture protection
echo     - Hidden from taskbar and Alt+Tab
echo     - Transparency control
echo     - Hotkeys: P+L+, (toggle), Ctrl+Shift+Up/Down (opacity)
echo     - No console window
echo     - Single native .exe
echo.
