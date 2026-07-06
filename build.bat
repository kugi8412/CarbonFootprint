@echo off
REM ============================================================
REM Carbon Footprint Tracker - Windows Build Script
REM Requires: CMake 3.14+, Visual Studio or MinGW
REM ============================================================

echo ===================================
echo  Carbon Footprint Tracker - Build
echo ===================================
echo.

REM Check for CMake
where cmake >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: CMake not found in PATH.
    echo Please install CMake from https://cmake.org/download/
    exit /b 1
)

REM Create build directory
if not exist build mkdir build
cd build

REM ============================================================
REM Pick a generator that works from a *plain* PowerShell / cmd
REM ============================================================
set "GEN_ARGS="

REM 1) Prefer Visual Studio if it is installed (uses vswhere).
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" (
    for /f "usebackq tokens=*" %%v in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property catalog_productLineVersion 2^>nul`) do (
        if "%%v"=="2022" set "GEN_ARGS=-G "Visual Studio 17 2022" -A x64"
        if "%%v"=="2019" set "GEN_ARGS=-G "Visual Studio 16 2019" -A x64"
        if "%%v"=="2017" set "GEN_ARGS=-G "Visual Studio 15 2017 Win64""
    )
)

REM 2) Otherwise fall back to MinGW (gcc) if it is on PATH.
if not defined GEN_ARGS (
    where gcc >nul 2>&1 && set "GEN_ARGS=-G "MinGW Makefiles""
)

REM Configure with CMake
echo Configuring project...
if defined GEN_ARGS (
    echo Using generator: %GEN_ARGS%
    cmake .. %GEN_ARGS% -DCMAKE_BUILD_TYPE=Release
) else (
    cmake .. -DCMAKE_BUILD_TYPE=Release
)
if %ERRORLEVEL% neq 0 (
    echo ERROR: CMake configuration failed.
    echo Install Visual Studio Desktop C++ or MinGW-w64, or run this from
    echo the Developer PowerShell for VS.
    cd ..
    exit /b 1
)

REM Build
echo.
echo Building...
cmake --build . --config Release
if %ERRORLEVEL% neq 0 (
    echo ERROR: Build failed.
    cd ..
    exit /b 1
)

echo.
echo ===================================
echo  Build successful!
echo  Binary: build\Release\carbon_tracker.exe
echo ===================================
echo.
echo Usage:
echo   build\Release\carbon_tracker.exe
echo   build\Release\carbon_tracker.exe --start --zone PL
echo   build\Release\carbon_tracker.exe --help
echo.

cd ..
