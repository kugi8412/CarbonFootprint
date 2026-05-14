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

REM Configure with CMake
echo Configuring project...
cmake .. -DCMAKE_BUILD_TYPE=Release
if %ERRORLEVEL% neq 0 (
    echo ERROR: CMake configuration failed.
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
