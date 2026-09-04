@echo off
:: ─────────────────────────────────────────────────────────────────────────
:: build_driver.bat
:: Compiles the TopMost Shield kernel driver using MSVC + WDK
:: ─────────────────────────────────────────────────────────────────────────

echo ========================================================
echo   TopMost Shield - Driver Build Script
echo ========================================================
echo.

:: ── Paths (avoid CL/LINK - they are reserved MSVC env vars) ──
set "MSVC_ROOT=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207"
set "SDK_INC=C:\Program Files (x86)\Windows Kits\10\Include\10.0.22621.0"
set "SDK_LIB=C:\Program Files (x86)\Windows Kits\10\lib\10.0.22621.0"
set "COMPILER=%MSVC_ROOT%\bin\Hostx64\x64\cl.exe"
set "LINKER=%MSVC_ROOT%\bin\Hostx64\x64\link.exe"

set "SRC_DIR=%~dp0"
set "OUT_DIR=%~dp0build"

:: Create build output directory
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo [1/2] Compiling topmost_driver.c ...

"%COMPILER%" /c /Zi /nologo /W4 /WX- ^
    /D _WIN64 /D _AMD64_ /D AMD64 ^
    /D NTDDI_VERSION=0x0A00000C ^
    /D _KERNEL_MODE ^
    /D _WIN32_WINNT=0x0A00 ^
    /D WINVER=0x0A00 ^
    /D WINNT=1 ^
    /D NDEBUG ^
    /D POOL_NX_OPTIN=1 ^
    /kernel /GS- /Gy ^
    /Zp8 /Gz ^
    /O2 ^
    /I"%SDK_INC%\km" ^
    /I"%SDK_INC%\km\crt" ^
    /I"%SDK_INC%\shared" ^
    /I"%SDK_INC%\um" ^
    /I"%MSVC_ROOT%\include" ^
    /I"%SRC_DIR%." ^
    /Fo"%OUT_DIR%\topmost_driver.obj" ^
    "%SRC_DIR%topmost_driver.c"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Compilation failed!
    exit /b 1
)
echo [OK] Compilation successful.
echo.

echo [2/2] Linking topmost_driver.sys ...

"%LINKER%" /nologo /NODEFAULTLIB ^
    /ENTRY:DriverEntry ^
    /DRIVER:WDM ^
    /SUBSYSTEM:NATIVE ^
    /MACHINE:X64 ^
    /OUT:"%OUT_DIR%\topmost_driver.sys" ^
    /PDB:"%OUT_DIR%\topmost_driver.pdb" ^
    /MAP:"%OUT_DIR%\topmost_driver.map" ^
    /RELEASE ^
    /INTEGRITYCHECK ^
    "%OUT_DIR%\topmost_driver.obj" ^
    "%SDK_LIB%\km\x64\ntoskrnl.lib" ^
    "%SDK_LIB%\km\x64\hal.lib" ^
    "%SDK_LIB%\km\x64\wmilib.lib" ^
    "%SDK_LIB%\km\x64\BufferOverflowFastFailK.lib" ^
    "%MSVC_ROOT%\lib\x64\libcmt.lib"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Linking failed!
    exit /b 1
)

echo [OK] Linking successful.
echo.

:: Copy .sys to driver root
copy "%OUT_DIR%\topmost_driver.sys" "%SRC_DIR%topmost_driver.sys" >nul
echo ─────────────────────────────────────────────────────
echo   BUILD COMPLETE
echo   Output: %OUT_DIR%\topmost_driver.sys
echo   Copied: %SRC_DIR%topmost_driver.sys
echo ─────────────────────────────────────────────────────
echo.
