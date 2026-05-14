#!/bin/bash
# ============================================================
# Carbon Footprint Tracker - Linux/Mac Build Script
# Requires: CMake 3.14+, GCC/Clang
# ============================================================

set -e

echo "==================================="
echo " Carbon Footprint Tracker - Build"
echo "==================================="
echo

# Check for CMake
if ! command -v cmake &> /dev/null; then
    echo "ERROR: CMake not found."
    echo "Install with:"
    echo "  Ubuntu/Debian: sudo apt install cmake build-essential"
    echo "  Fedora:        sudo dnf install cmake gcc-c++"
    echo "  macOS:         brew install cmake"
    exit 1
fi

# Check for compiler
if ! command -v g++ &> /dev/null && ! command -v clang++ &> /dev/null; then
    echo "ERROR: No C++ compiler found."
    echo "Install with:"
    echo "  Ubuntu/Debian: sudo apt install build-essential"
    echo "  Fedora:        sudo dnf install gcc-c++"
    echo "  macOS:         xcode-select --install"
    exit 1
fi

# Optional: check for X11 dev headers on Linux
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if ! pkg-config --exists x11 2>/dev/null; then
        echo "WARNING: X11 development libraries not found."
        echo "  Active window detection will be limited."
        echo "  Install with: sudo apt install libx11-dev"
        echo
    fi
fi

# Create build directory
mkdir -p build
cd build

# Configure
cmake .. -DCMAKE_BUILD_TYPE=Release

# Build
echo
cmake --build . -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)

echo
echo "==================================="
echo " Build successful!"
echo " Binary: build/carbon_tracker"
echo "==================================="
echo
echo "Usage:"
echo "  ./build/carbon_tracker"
echo "  ./build/carbon_tracker --start --zone PL"
echo "  ./build/carbon_tracker --start --daemon --zone US-CAL"
echo "  ./build/carbon_tracker --help"
echo

cd ..
