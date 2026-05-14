#pragma once

// ============================================================
// Platform Detection & Common Abstractions
// ============================================================

// --- Platform detection ---
#if defined(_WIN32) || defined(_WIN64)
    #define PLATFORM_WINDOWS 1
#elif defined(__APPLE__) && defined(__MACH__)
    #define PLATFORM_MAC 1
#elif defined(__linux__)
    #define PLATFORM_LINUX 1
#else
    #error "Unsupported platform"
#endif

#include <string>
#include <vector>
#include <map>
#include <chrono>
#include <ctime>
#include <iostream>
#include <fstream>
#include <sstream>
#include <thread>
#include <mutex>
#include <atomic>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <functional>
#include <numeric>
#include <array>

#ifdef PLATFORM_WINDOWS
    #ifndef WIN32_LEAN_AND_MEAN
        #define WIN32_LEAN_AND_MEAN
    #endif
    #ifndef NOMINMAX
        #define NOMINMAX
    #endif
    #include <windows.h>
    #include <psapi.h>
    #include <winhttp.h>
    #include <tlhelp32.h>
    #pragma comment(lib, "psapi.lib")
    #pragma comment(lib, "winhttp.lib")
#endif

#ifdef PLATFORM_LINUX
    #include <unistd.h>
    #include <signal.h>
    #include <sys/stat.h>
    #include <sys/types.h>
    #include <dirent.h>
    #include <fcntl.h>
    #ifdef HAS_X11
        #include <X11/Xlib.h>
        #include <X11/Xatom.h>
    #endif
#endif

#ifdef PLATFORM_MAC
    #include <unistd.h>
    #include <signal.h>
    #include <sys/types.h>
    #include <sys/sysctl.h>
    #include <fcntl.h>
    #include <mach/mach.h>
    #include <mach/processor_info.h>
    #include <mach/mach_host.h>
#endif

#ifdef HAS_NVML
    #include <nvml.h>
#endif

// Time helpers
namespace TimeUtil {
    inline std::string Now() {
        auto now = std::chrono::system_clock::now();
        auto t = std::chrono::system_clock::to_time_t(now);
        std::tm tm_buf{};
#ifdef PLATFORM_WINDOWS
        localtime_s(&tm_buf, &t);
#else
        localtime_r(&t, &tm_buf);
#endif
        char buf[64];
        std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &tm_buf);
        return std::string(buf);
    }

    inline int CurrentHour() {
        auto now = std::chrono::system_clock::now();
        auto t = std::chrono::system_clock::to_time_t(now);
        std::tm tm_buf{};
#ifdef PLATFORM_WINDOWS
        localtime_s(&tm_buf, &t);
#else
        localtime_r(&t, &tm_buf);
#endif
        return tm_buf.tm_hour;
    }

    inline double SecondsSinceEpoch() {
        auto now = std::chrono::system_clock::now();
        return std::chrono::duration<double>(now.time_since_epoch()).count();
    }

    inline std::string FormatDuration(double seconds) {
        int h = static_cast<int>(seconds) / 3600;
        int m = (static_cast<int>(seconds) % 3600) / 60;
        int s = static_cast<int>(seconds) % 60;
        std::ostringstream oss;
        oss << h << "h " << m << "m " << s << "s";
        return oss.str();
    }
}
