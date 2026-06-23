cmake_minimum_required(VERSION 3.14)
project(CarbonFootprint VERSION 1.1.3 LANGUAGES CXX)

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
    find_library(APPKIT_LIB AppKit)
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
    find_library(NVML_LIB nvidia-ml HINTS
        "C:/Program Files/NVIDIA Corporation/NVSMI"
        "/usr/lib/x86_64-linux-gnu"
        "/usr/lib64"
    )
    if(NVML_LIB)
        target_link_libraries(carbon_tracker PRIVATE ${NVML_LIB})
        target_compile_definitions(carbon_tracker PRIVATE HAS_NVML)
        message(STATUS "NVML found: ${NVML_LIB}")
    else()
        message(WARNING "NVML not found, GPU monitoring will use estimates")
    endif()
endif()

# Optional: libcurl
option(USE_CURL "Use libcurl for HTTP requests" OFF)
if(USE_CURL)
    find_package(CURL QUIET)
    if(CURL_FOUND)
        target_link_libraries(carbon_tracker PRIVATE CURL::libcurl)
        target_compile_definitions(carbon_tracker PRIVATE HAS_CURL)
        message(STATUS "libcurl found")
    else()
        message(WARNING "libcurl not found, using platform HTTP or system curl")
    endif()
endif()

# Installation
install(TARGETS carbon_tracker DESTINATION bin)
