#include "hardware_detect.h"

// ============================================================
// Hardware Detection Implementation
// ============================================================

bool HardwareDetect::ContainsIgnoreCase(const std::string& haystack, const std::string& needle) {
    std::string h = haystack, n = needle;
    std::transform(h.begin(), h.end(), h.begin(), ::tolower);
    std::transform(n.begin(), n.end(), n.begin(), ::tolower);
    return h.find(n) != std::string::npos;
}

// CPU TDP Lookup Table
const std::vector<HardwareDetect::CpuTdpEntry>& HardwareDetect::GetCpuTdpTable() {
    static const std::vector<CpuTdpEntry> table = {
        // Intel Mobile (U/P series - laptops)
        {"i7-14", 28}, {"i7-13", 28}, {"i7-12", 28}, {"i5-14", 28}, {"i5-13", 28}, {"i5-12", 28},
        {"i7-11", 28}, {"i5-11", 28}, {"i7-10", 15}, {"i5-10", 15},
        {"i9-14900H", 45}, {"i9-13900H", 45}, {"i7-14700H", 45}, {"i7-13700H", 45},
        {"i5-14500H", 45}, {"i5-13500H", 45},
        // Intel Desktop (K/KF/S series)
        {"i9-14900K", 125}, {"i9-13900K", 125}, {"i9-12900K", 125},
        {"i7-14700K", 125}, {"i7-13700K", 125}, {"i7-12700K", 125},
        {"i5-14600K", 125}, {"i5-13600K", 125}, {"i5-12600K", 125},
        {"i9-14900", 65}, {"i9-13900", 65}, {"i7-14700", 65}, {"i7-13700", 65},
        {"i5-14600", 65}, {"i5-14400", 65}, {"i5-13600", 65}, {"i5-13400", 65},
        {"i3-14", 60}, {"i3-13", 60}, {"i3-12", 60},
        // Intel generic patterns
        {"Core Ultra 9", 45}, {"Core Ultra 7", 28}, {"Core Ultra 5", 28},
        {"Xeon", 105}, {"Pentium", 35}, {"Celeron", 15},
        // AMD Ryzen Mobile
        {"7840U", 28}, {"7640U", 28}, {"7530U", 15}, {"6800U", 28},
        {"Ryzen 9 7945HX", 55}, {"Ryzen 7 7840H", 45}, {"Ryzen 5 7640H", 45},
        {"Ryzen 9 6900H", 45}, {"Ryzen 7 6800H", 45}, {"Ryzen 5 6600H", 45},
        // AMD Ryzen Desktop
        {"Ryzen 9 7950X", 170}, {"Ryzen 9 7900X", 170}, {"Ryzen 7 7700X", 105},
        {"Ryzen 5 7600X", 105}, {"Ryzen 9 5950X", 105}, {"Ryzen 9 5900X", 105},
        {"Ryzen 7 5800X", 105}, {"Ryzen 5 5600X", 65}, {"Ryzen 5 5600", 65},
        {"Ryzen 9 9950X", 170}, {"Ryzen 9 9900X", 120}, {"Ryzen 7 9700X", 65},
        {"Ryzen 5 9600X", 65},
        // AMD generic patterns
        {"Ryzen 9", 105}, {"Ryzen 7", 65}, {"Ryzen 5", 65}, {"Ryzen 3", 45},
        {"Ryzen Threadripper", 280},
        // Apple Silicon
        {"M1 Pro", 30}, {"M1 Max", 40}, {"M1 Ultra", 60}, {"M1", 15},
        {"M2 Pro", 30}, {"M2 Max", 40}, {"M2 Ultra", 60}, {"M2", 15},
        {"M3 Pro", 30}, {"M3 Max", 40}, {"M3 Ultra", 60}, {"M3", 22},
        {"M4 Pro", 30}, {"M4 Max", 40}, {"M4", 22},
    };
    return table;
}

// GPU TDP Lookup Table
const std::vector<HardwareDetect::GpuTdpEntry>& HardwareDetect::GetGpuTdpTable() {
    static const std::vector<GpuTdpEntry> table = {
        // NVIDIA RTX 40 series
        {"RTX 4090", 450}, {"RTX 4080", 320}, {"RTX 4070 Ti", 285}, {"RTX 4070", 200},
        {"RTX 4060 Ti", 160}, {"RTX 4060", 115}, {"RTX 4050", 115},
        // NVIDIA RTX 40 Mobile
        {"RTX 4090 Laptop", 150}, {"RTX 4080 Laptop", 150}, {"RTX 4070 Laptop", 115},
        {"RTX 4060 Laptop", 100}, {"RTX 4050 Laptop", 75},
        // NVIDIA RTX 30 series
        {"RTX 3090 Ti", 450}, {"RTX 3090", 350}, {"RTX 3080 Ti", 350}, {"RTX 3080", 320},
        {"RTX 3070 Ti", 290}, {"RTX 3070", 220}, {"RTX 3060 Ti", 200}, {"RTX 3060", 170},
        {"RTX 3050", 130},
        // NVIDIA RTX 50 series
        {"RTX 5090", 575}, {"RTX 5080", 360}, {"RTX 5070 Ti", 300}, {"RTX 5070", 250},
        // NVIDIA GTX
        {"GTX 1660 Ti", 120}, {"GTX 1660 SUPER", 125}, {"GTX 1660", 120},
        {"GTX 1650 SUPER", 100}, {"GTX 1650", 75}, {"GTX 1080 Ti", 250},
        {"GTX 1080", 180}, {"GTX 1070", 150}, {"GTX 1060", 120},
        // NVIDIA generic
        {"RTX", 200}, {"GTX", 120}, {"MX550", 25}, {"MX450", 25}, {"MX350", 25},
        // AMD Radeon
        {"RX 7900 XTX", 355}, {"RX 7900 XT", 315}, {"RX 7800 XT", 263},
        {"RX 7700 XT", 245}, {"RX 7600", 165},
        {"RX 6900 XT", 300}, {"RX 6800 XT", 300}, {"RX 6800", 250},
        {"RX 6700 XT", 230}, {"RX 6600 XT", 160}, {"RX 6600", 132},
        {"Radeon 780M", 15}, {"Radeon 760M", 15}, {"Radeon 680M", 15},
        {"Radeon", 150},
        // Intel Arc
        {"Arc A770", 225}, {"Arc A750", 225}, {"Arc A580", 185}, {"Arc A380", 75},
        {"Intel Arc", 150},
        // Intel Integrated
        {"Intel Iris Xe", 15}, {"Intel UHD", 15}, {"Intel HD", 10},
        {"Iris Plus", 15}, {"Iris", 15},
    };
    return table;
}

// WINDOWS Implementation
#ifdef PLATFORM_WINDOWS

std::string HardwareDetect::DetectCpuName() {
    // Read from registry: HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0
    HKEY hKey;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,
            "HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0",
            0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        char value[256] = {};
        DWORD size = sizeof(value);
        DWORD type = REG_SZ;
        if (RegQueryValueExA(hKey, "ProcessorNameString", NULL, &type,
                (LPBYTE)value, &size) == ERROR_SUCCESS) {
            RegCloseKey(hKey);
            // Trim whitespace
            std::string name(value);
            size_t start = name.find_first_not_of(" \t");
            size_t end = name.find_last_not_of(" \t");
            if (start != std::string::npos)
                return name.substr(start, end - start + 1);
            return name;
        }
        RegCloseKey(hKey);
    }
    return "";
}

int HardwareDetect::DetectCpuCores() {
    SYSTEM_INFO sysInfo;
    GetSystemInfo(&sysInfo);
    // This returns logical processors, we want physical cores
    // Use GetLogicalProcessorInformation for more accuracy
    DWORD bufLen = 0;
    GetLogicalProcessorInformation(NULL, &bufLen);
    if (GetLastError() == ERROR_INSUFFICIENT_BUFFER) {
        std::vector<SYSTEM_LOGICAL_PROCESSOR_INFORMATION> buffer(
            bufLen / sizeof(SYSTEM_LOGICAL_PROCESSOR_INFORMATION));
        if (GetLogicalProcessorInformation(buffer.data(), &bufLen)) {
            int cores = 0;
            for (const auto& info : buffer) {
                if (info.Relationship == RelationProcessorCore) cores++;
            }
            if (cores > 0) return cores;
        }
    }
    return sysInfo.dwNumberOfProcessors;
}

int HardwareDetect::DetectCpuThreads() {
    SYSTEM_INFO sysInfo;
    GetSystemInfo(&sysInfo);
    return sysInfo.dwNumberOfProcessors;
}

std::string HardwareDetect::DetectGpuName() {
    // Use DXGI to enumerate adapters
    // Fallback: read from registry
    HKEY hKey;
    std::string bestGpu;

    // Enumerate display adapters from registry
    for (int i = 0; i < 10; i++) {
        std::string subKey = "SYSTEM\\CurrentControlSet\\Control\\Class\\"
            "{4d36e968-e325-11ce-bfc1-08002be10318}\\" +
            std::string(4 - std::to_string(i).length(), '0') + std::to_string(i);

        if (RegOpenKeyExA(HKEY_LOCAL_MACHINE, subKey.c_str(), 0, KEY_READ, &hKey) == ERROR_SUCCESS) {
            char value[256] = {};
            DWORD size = sizeof(value);
            DWORD type = REG_SZ;
            if (RegQueryValueExA(hKey, "DriverDesc", NULL, &type,
                    (LPBYTE)value, &size) == ERROR_SUCCESS) {
                std::string gpuName(value);
                // Prefer discrete GPU over integrated
                if (bestGpu.empty() ||
                    (!ContainsIgnoreCase(gpuName, "Intel") && !ContainsIgnoreCase(gpuName, "UHD") &&
                     !ContainsIgnoreCase(gpuName, "Iris"))) {
                    bestGpu = gpuName;
                }
            }
            RegCloseKey(hKey);
        }
    }
    return bestGpu;
}

bool HardwareDetect::DetectIsLaptop() {
    // Check if system has a battery
    SYSTEM_POWER_STATUS powerStatus;
    if (GetSystemPowerStatus(&powerStatus)) {
        // BatteryFlag: 128 = No system battery
        if (powerStatus.BatteryFlag != 128 && powerStatus.BatteryFlag != 255) {
            return true; // Has battery = laptop
        }
    }
    return false;
}

// LINUX Implementation
#elif defined(PLATFORM_LINUX)

std::string HardwareDetect::DetectCpuName() {
    std::ifstream cpuInfo("/proc/cpuinfo");
    std::string line;
    while (std::getline(cpuInfo, line)) {
        if (line.find("model name") != std::string::npos) {
            size_t pos = line.find(':');
            if (pos != std::string::npos) {
                std::string name = line.substr(pos + 1);
                size_t start = name.find_first_not_of(" \t");
                if (start != std::string::npos)
                    return name.substr(start);
            }
        }
    }
    return "";
}

int HardwareDetect::DetectCpuCores() {
    std::ifstream cpuInfo("/proc/cpuinfo");
    std::string line;
    int coreIds = 0;
    std::vector<int> seenCores;
    while (std::getline(cpuInfo, line)) {
        if (line.find("core id") != std::string::npos) {
            size_t pos = line.find(':');
            if (pos != std::string::npos) {
                int id = std::stoi(line.substr(pos + 1));
                if (std::find(seenCores.begin(), seenCores.end(), id) == seenCores.end()) {
                    seenCores.push_back(id);
                    coreIds++;
                }
            }
        }
    }
    if (coreIds > 0) return coreIds;

    // Fallback
    long nprocs = sysconf(_SC_NPROCESSORS_ONLN);
    return (nprocs > 0) ? static_cast<int>(nprocs) : 1;
}

int HardwareDetect::DetectCpuThreads() {
    long nprocs = sysconf(_SC_NPROCESSORS_ONLN);
    return (nprocs > 0) ? static_cast<int>(nprocs) : 1;
}

std::string HardwareDetect::DetectGpuName() {
    // Try nvidia-smi first for NVIDIA GPUs
    FILE* nvPipe = popen("nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null", "r");
    if (nvPipe) {
        char buffer[256];
        std::string nvGpu;
        if (fgets(buffer, sizeof(buffer), nvPipe) != nullptr) {
            nvGpu = std::string(buffer);
            size_t start = nvGpu.find_first_not_of(" \t");
            size_t end = nvGpu.find_last_not_of(" \t\n\r");
            if (start != std::string::npos)
                nvGpu = nvGpu.substr(start, end - start + 1);
        }
        pclose(nvPipe);
        if (!nvGpu.empty()) return nvGpu;
    }

    // Fallback to lspci
    FILE* pipe = popen("lspci 2>/dev/null | grep -i 'vga\\|3d\\|display'", "r");
    if (pipe) {
        char buffer[512];
        std::string bestGpu;
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            std::string line(buffer);
            // Extract the GPU name after the last colon
            size_t pos = line.rfind(':');
            if (pos != std::string::npos) {
                std::string gpu = line.substr(pos + 1);
                size_t start = gpu.find_first_not_of(" \t");
                size_t end = gpu.find_last_not_of(" \t\n\r");
                if (start != std::string::npos)
                    gpu = gpu.substr(start, end - start + 1);
                // Prefer discrete GPU
                if (bestGpu.empty() ||
                    (!ContainsIgnoreCase(gpu, "Intel") && !ContainsIgnoreCase(gpu, "UHD"))) {
                    bestGpu = gpu;
                }
            }
        }
        pclose(pipe);
        if (!bestGpu.empty()) return bestGpu;
    }
    return "";
}

bool HardwareDetect::DetectIsLaptop() {
    // Check if running on WSL
    bool isWsl = false;
    std::ifstream procVersion("/proc/version");
    if (procVersion.is_open()) {
        std::string versionStr;
        std::getline(procVersion, versionStr);
        std::transform(versionStr.begin(), versionStr.end(), versionStr.begin(), ::tolower);
        if (versionStr.find("microsoft") != std::string::npos ||
            versionStr.find("wsl") != std::string::npos) {
            isWsl = true;
        }
    }

    if (isWsl) {
        // On WSL, battery detection is unreliable; use chassis type
        std::ifstream chassis("/sys/class/dmi/id/chassis_type");
        if (chassis.is_open()) {
            int type;
            chassis >> type;
            if (type == 9 || type == 10 || type == 14 || type == 31 || type == 32) return true;
        }
        return false;
    }

    // Native Linux: check for battery in power_supply
    DIR* dir = opendir("/sys/class/power_supply");
    if (dir) {
        struct dirent* entry;
        while ((entry = readdir(dir)) != nullptr) {
            std::string typePath = std::string("/sys/class/power_supply/") + entry->d_name + "/type";
            std::ifstream typeFile(typePath);
            if (typeFile.is_open()) {
                std::string type;
                typeFile >> type;
                if (type == "Battery") {
                    closedir(dir);
                    return true;
                }
            }
        }
        closedir(dir);
    }

    // Fallback: check chassis type from DMI
    std::ifstream chassis("/sys/class/dmi/id/chassis_type");
    if (chassis.is_open()) {
        int type;
        chassis >> type;
        // 9=Laptop, 10=Notebook, 14=Sub-Notebook, 31=Convertible, 32=Detachable
        if (type == 9 || type == 10 || type == 14 || type == 31 || type == 32) return true;
    }
    return false;
}

// macOS Implementation
#elif defined(PLATFORM_MAC)

std::string HardwareDetect::DetectCpuName() {
    char buf[256] = {};
    size_t bufLen = sizeof(buf);
    if (sysctlbyname("machdep.cpu.brand_string", buf, &bufLen, NULL, 0) == 0) {
        return std::string(buf);
    }
    return "";
}

int HardwareDetect::DetectCpuCores() {
    int cores = 0;
    size_t size = sizeof(cores);
    if (sysctlbyname("hw.physicalcpu", &cores, &size, NULL, 0) == 0) return cores;
    return 1;
}

int HardwareDetect::DetectCpuThreads() {
    int threads = 0;
    size_t size = sizeof(threads);
    if (sysctlbyname("hw.logicalcpu", &threads, &size, NULL, 0) == 0) return threads;
    return 1;
}

std::string HardwareDetect::DetectGpuName() {
    FILE* pipe = popen("system_profiler SPDisplaysDataType 2>/dev/null | grep 'Chipset Model'", "r");
    if (pipe) {
        char buffer[256];
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            std::string line(buffer);
            size_t pos = line.find(':');
            if (pos != std::string::npos) {
                std::string name = line.substr(pos + 1);
                size_t start = name.find_first_not_of(" \t");
                size_t end = name.find_last_not_of(" \t\n\r");
                if (start != std::string::npos) {
                    pclose(pipe);
                    return name.substr(start, end - start + 1);
                }
            }
        }
        pclose(pipe);
    }
    return "";
}

bool HardwareDetect::DetectIsLaptop() {
    FILE* pipe = popen("system_profiler SPHardwareDataType 2>/dev/null | grep 'Model Name'", "r");
    if (pipe) {
        char buffer[256];
        while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
            std::string line(buffer);
            if (ContainsIgnoreCase(line, "MacBook")) {
                pclose(pipe);
                return true;
            }
        }
        pclose(pipe);
    }
    return false;
}

#endif


double HardwareDetect::EstimateCpuTdp(const std::string& cpuName, int cores) {
    if (!cpuName.empty()) {
        for (const auto& entry : GetCpuTdpTable()) {
            if (ContainsIgnoreCase(cpuName, entry.pattern)) {
                return entry.tdpWatts;
            }
        }
    }
    // Fallback heuristic based on core count
    if (cores <= 4) return 35.0;
    if (cores <= 6) return 65.0;
    if (cores <= 8) return 80.0;
    if (cores <= 12) return 105.0;
    return 125.0;
}

double HardwareDetect::EstimateGpuTdp(const std::string& gpuName) {
    if (!gpuName.empty()) {
        for (const auto& entry : GetGpuTdpTable()) {
            if (ContainsIgnoreCase(gpuName, entry.pattern)) {
                return entry.tdpWatts;
            }
        }
    }
    return 15.0; // Assume integrated graphics
}

double HardwareDetect::EstimateBasePower(bool isLaptop) {
    return isLaptop ? 15.0 : 40.0; // RAM, disks, fans, PSU loss
}

HardwareInfo HardwareDetect::DetectAll() {
    HardwareInfo info{};

    info.cpuName = DetectCpuName();
    info.cpuCores = DetectCpuCores();
    info.cpuThreads = DetectCpuThreads();
    info.cpuDetected = !info.cpuName.empty();
    info.cpuTdpWatts = EstimateCpuTdp(info.cpuName, info.cpuCores);

    info.gpuName = DetectGpuName();
    info.gpuDetected = !info.gpuName.empty();
    info.gpuTdpWatts = EstimateGpuTdp(info.gpuName);

    info.isLaptop = DetectIsLaptop();
    info.laptopDetected = true;
    info.baseSystemWatts = EstimateBasePower(info.isLaptop);

    return info;
}

void HardwareDetect::PrintDetectedHardware(const HardwareInfo& info) {
    std::cout << "\n=== AUTO-DETECTED HARDWARE ===\n\n";

    if (info.cpuDetected) {
        std::cout << "  CPU:  " << info.cpuName << "\n";
        std::cout << "        " << info.cpuCores << " cores / " << info.cpuThreads << " threads\n";
        std::cout << "        Estimated TDP: " << info.cpuTdpWatts << " W\n";
    } else {
        std::cout << "  CPU:  (not detected) - using estimate: " << info.cpuTdpWatts << " W\n";
    }

    if (info.gpuDetected) {
        std::cout << "  GPU:  " << info.gpuName << "\n";
        std::cout << "        Estimated TDP: " << info.gpuTdpWatts << " W\n";
    } else {
        std::cout << "  GPU:  (not detected) - using integrated estimate: " << info.gpuTdpWatts << " W\n";
    }

    std::cout << "  Type: " << (info.isLaptop ? "Laptop" : "Desktop") << "\n";
    std::cout << "  Base: " << info.baseSystemWatts << " W (RAM, disks, fans)\n";
    std::cout << "\n  Use 'Configure system parameters' to override any value.\n";
}
