cmake_minimum_required(VERSION 3.14)

# Version from carbon_tracker/_version.py
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/carbon_tracker/_version.py" _CFT_VERSION_PY)
string(REGEX MATCH "__version__ = \"([0-9]+\\.[0-9]+\\.[0-9]+)\"" _ "${_CFT_VERSION_PY}")
project(CarbonFootprint VERSION ${CMAKE_MATCH_1} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Sources
set(SOURCES
    src/main.cpp
    src/process_monitor.cpp
    src/power_monitor.cpp
    src/screen_monitor.cpp
    src/carbon_api.cpp
    src/carbon_engine.cpp
    src/report.cpp
    src/daemon.cpp
    src/hardware_detect.cpp
)

add_executable(carbon_tracker ${SOURCES})
target_include_directories(carbon_tracker PRIVATE include)

# Propagate the project version into the binary so the banner stays in sync.
target_compile_definitions(carbon_tracker PRIVATE CARBON_VERSION="${PROJECT_VERSION}")

# Platform-specific linking
if(WIN32)
    target_link_libraries(carbon_tracker PRIVATE psapi winhttp)
    target_compile_definitions(carbon_tracker PRIVATE PLATFORM_WINDOWS)
elseif(APPLE)
    find_library(IOKIT_LIB IOKit)
    find_library(COREFOUND_LIB CoreFoundation)
    target_link_libraries(carbon_tracker PRIVATE ${IOKIT_LIB} ${COREFOUND_LIB} pthread)
    target_compile_definitions(carbon_tracker PRIVATE PLATFORM_MAC)
else()
    target_link_libraries(carbon_tracker PRIVATE pthread)
    target_compile_definitions(carbon_tracker PRIVATE PLATFORM_LINUX)
    # Try to find X11 for active window detection
    find_package(X11 QUIET)
    if(X11_FOUND)
        target_link_libraries(carbon_tracker PRIVATE ${X11_LIBRARIES})
        target_include_directories(carbon_tracker PRIVATE ${X11_INCLUDE_DIR})
        target_compile_definitions(carbon_tracker PRIVATE HAS_X11)
    endif()
endif()

# Optional: NVIDIA NVML
option(USE_NVML "Enable NVIDIA GPU monitoring via NVML" OFF)
if(USE_NVML)
    # nvml.h comes with the CUDA toolkit; the library is nvml.lib on Windows
    # and libnvidia-ml.so elsewhere
    find_package(CUDAToolkit QUIET)
    find_path(NVML_INCLUDE_DIR nvml.h HINTS ${CUDAToolkit_INCLUDE_DIRS} "/usr/local/cuda/include")
    find_library(NVML_LIB NAMES nvml nvidia-ml HINTS
        ${CUDAToolkit_LIBRARY_DIR}
        "C:/Program Files/NVIDIA Corporation/NVSMI"
        "/usr/lib/x86_64-linux-gnu"
        "/usr/lib64"
        "/usr/local/cuda/lib64/stubs"
    )
    if(NVML_LIB AND NVML_INCLUDE_DIR)
        target_include_directories(carbon_tracker PRIVATE ${NVML_INCLUDE_DIR})
        target_link_libraries(carbon_tracker PRIVATE ${NVML_LIB})
        target_compile_definitions(carbon_tracker PRIVATE HAS_NVML)
        message(STATUS "NVML found: ${NVML_LIB}")
    else()
        message(WARNING "NVML (nvml.h + library) not found, GPU power will use nvidia-smi / estimates")
    endif()
endif()

# Installation
install(TARGETS carbon_tracker DESTINATION bin)
