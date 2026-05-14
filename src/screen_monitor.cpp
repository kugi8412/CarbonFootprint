#include "screen_monitor.h"

// ============================================================
// Screen Monitor Implementation - Cross-platform
// ============================================================

#ifdef PLATFORM_WINDOWS

double ScreenMonitor::GetBrightness() {
    // Use WMI via PowerShell to get brightness (works on laptops)
    // For desktops, brightness detection is not supported via standard APIs
    FILE* pipe = _popen("powershell -NoProfile -Command \"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness\" 2>nul", "r");
    if (!pipe) return -1.0;

    char buffer[64];
    std::string result;
    while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
        result += buffer;
    }
    int exitCode = _pclose(pipe);
    if (exitCode != 0 || result.empty()) return -1.0;

    try {
        int brightness = std::stoi(result);
        return std::min(std::max(brightness / 100.0, 0.0), 1.0);
    } catch (...) {
        return -1.0;
    }
}

#elif defined(PLATFORM_LINUX)

double ScreenMonitor::GetBrightness() {
    // Try common backlight paths
    const std::vector<std::string> paths = {
        "/sys/class/backlight/intel_backlight",
        "/sys/class/backlight/amdgpu_bl0",
        "/sys/class/backlight/acpi_video0",
        "/sys/class/backlight/nvidia_backlight"
    };

    for (const auto& basePath : paths) {
        std::ifstream maxFile(basePath + "/max_brightness");
        std::ifstream curFile(basePath + "/brightness");
        if (maxFile.is_open() && curFile.is_open()) {
            int maxBright, curBright;
            maxFile >> maxBright;
            curFile >> curBright;
            if (maxBright > 0) {
                return std::min(std::max((double)curBright / (double)maxBright, 0.0), 1.0);
            }
        }
    }

    // Try using xbacklight command
    FILE* pipe = popen("xbacklight -get 2>/dev/null", "r");
    if (pipe) {
        char buffer[64];
        std::string result;
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            result += buffer;
        }
        int exitCode = pclose(pipe);
        if (exitCode == 0 && !result.empty()) {
            try {
                double brightness = std::stod(result);
                return std::min(std::max(brightness / 100.0, 0.0), 1.0);
            } catch (...) {}
        }
    }

    return -1.0;
}

#elif defined(PLATFORM_MAC)

double ScreenMonitor::GetBrightness() {
    // Use AppleScript to get brightness on macOS
    FILE* pipe = popen("osascript -e 'tell application \"System Events\" to get value of slider 1 of group 1 of group 2 of toolbar 1 of window 1 of application process \"SystemUIServer\"' 2>/dev/null", "r");
    if (pipe) {
        char buffer[64];
        std::string result;
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            result += buffer;
        }
        pclose(pipe);
        if (!result.empty()) {
            try {
                double brightness = std::stod(result);
                return std::min(std::max(brightness, 0.0), 1.0);
            } catch (...) {}
        }
    }

    // Fallback: try brightness command-line tool
    pipe = popen("brightness -l 2>/dev/null | grep 'display 0' | awk '{print $NF}'", "r");
    if (pipe) {
        char buffer[64];
        std::string result;
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            result += buffer;
        }
        pclose(pipe);
        if (!result.empty()) {
            try {
                return std::min(std::max(std::stod(result), 0.0), 1.0);
            } catch (...) {}
        }
    }

    return -1.0;
}

#endif

// Platform-independent
double ScreenMonitor::EstimateScreenPower(double brightness, bool isLaptop) {
    if (brightness < 0.0) brightness = 0.5; // Default to 50% if unknown

    if (isLaptop) {
        // Laptop screen: 2W (min) to 10W (max brightness)
        return 2.0 + brightness * 8.0;
    } else {
        // Desktop monitor: 10W (min) to 40W (max brightness)
        return 10.0 + brightness * 30.0;
    }
}
