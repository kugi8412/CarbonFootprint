#include "process_monitor.h"

// ============================================================
// Process Monitor Implementation - Cross-platform
// ============================================================

// Static members
std::map<std::string, PerProcessCpuState> ProcessMonitor::processStates_;
std::mutex ProcessMonitor::statesMutex_;

// Windows Implementation
#ifdef PLATFORM_WINDOWS

std::vector<ProcessInfo> ProcessMonitor::ListRunningProcesses() {
    std::vector<ProcessInfo> processes;
    HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnapshot == INVALID_HANDLE_VALUE) return processes;

    PROCESSENTRY32 pe;
    pe.dwSize = sizeof(PROCESSENTRY32);

    if (Process32First(hSnapshot, &pe)) {
        do {
            ProcessInfo info;
            info.pid = pe.th32ProcessID;
            info.name = std::string(pe.szExeFile);
            info.cpuPercent = 0.0;
            processes.push_back(info);
        } while (Process32Next(hSnapshot, &pe));
    }
    CloseHandle(hSnapshot);

    // Remove duplicates (keep unique process names)
    std::sort(processes.begin(), processes.end(),
        [](const ProcessInfo& a, const ProcessInfo& b) { return a.name < b.name; });
    processes.erase(
        std::unique(processes.begin(), processes.end(),
            [](const ProcessInfo& a, const ProcessInfo& b) { return a.name == b.name; }),
        processes.end());

    return processes;
}

std::string ProcessMonitor::GetActiveProcessName() {
    HWND hwnd = GetForegroundWindow();
    if (hwnd == NULL) return "Unknown";

    DWORD processId;
    GetWindowThreadProcessId(hwnd, &processId);

    HANDLE hProcess = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, processId);
    if (hProcess == NULL) return "Unknown";

    char processName[MAX_PATH] = "<unknown>";
    HMODULE hMod;
    DWORD cbNeeded;

    if (EnumProcessModules(hProcess, &hMod, sizeof(hMod), &cbNeeded)) {
        GetModuleBaseNameA(hProcess, hMod, processName, sizeof(processName));
    }

    CloseHandle(hProcess);
    return std::string(processName);
}

std::string ProcessMonitor::GetActiveWindowTitle() {
    HWND hwnd = GetForegroundWindow();
    if (hwnd == NULL) return "";

    char title[512] = {};
    GetWindowTextA(hwnd, title, sizeof(title));
    return std::string(title);
}

static ULARGE_INTEGER lastCpuIdle, lastCpuKernel, lastCpuUser;
static bool cpuInitialized = false;

double ProcessMonitor::GetSystemCpuUsage() {
    FILETIME idleTime, kernelTime, userTime;
    if (!GetSystemTimes(&idleTime, &kernelTime, &userTime)) return 0.0;

    ULARGE_INTEGER idle, kernel, user;
    idle.LowPart = idleTime.dwLowDateTime;    idle.HighPart = idleTime.dwHighDateTime;
    kernel.LowPart = kernelTime.dwLowDateTime; kernel.HighPart = kernelTime.dwHighDateTime;
    user.LowPart = userTime.dwLowDateTime;     user.HighPart = userTime.dwHighDateTime;

    if (!cpuInitialized) {
        lastCpuIdle = idle;
        lastCpuKernel = kernel;
        lastCpuUser = user;
        cpuInitialized = true;
        return 0.0;
    }

    ULONGLONG idleDiff = idle.QuadPart - lastCpuIdle.QuadPart;
    ULONGLONG kernelDiff = kernel.QuadPart - lastCpuKernel.QuadPart;
    ULONGLONG userDiff = user.QuadPart - lastCpuUser.QuadPart;

    lastCpuIdle = idle;
    lastCpuKernel = kernel;
    lastCpuUser = user;

    ULONGLONG totalDiff = kernelDiff + userDiff;
    if (totalDiff == 0) return 0.0;

    return (1.0 - (double)idleDiff / (double)totalDiff) * 100.0;
}

double ProcessMonitor::GetProcessCpuUsage(const std::string& processName) {
    auto result = GetMultiProcessCpuUsage({processName});
    auto it = result.find(processName);
    if (it != result.end()) return it->second;
    return 0.0;
}

std::vector<unsigned long> ProcessMonitor::GetProcessPids(const std::string& processName) {
    std::vector<unsigned long> pids;
    HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnapshot == INVALID_HANDLE_VALUE) return pids;

    PROCESSENTRY32 pe;
    pe.dwSize = sizeof(PROCESSENTRY32);
    std::string lowerTarget = processName;
    std::transform(lowerTarget.begin(), lowerTarget.end(), lowerTarget.begin(), ::tolower);

    if (Process32First(hSnapshot, &pe)) {
        do {
            std::string pName(pe.szExeFile);
            std::transform(pName.begin(), pName.end(), pName.begin(), ::tolower);
            // Match with and without .exe
            std::string lowerNoExt = lowerTarget;
            if (lowerNoExt.size() > 4 && lowerNoExt.substr(lowerNoExt.size()-4) == ".exe")
                lowerNoExt = lowerNoExt.substr(0, lowerNoExt.size()-4);
            std::string pNameNoExt = pName;
            if (pNameNoExt.size() > 4 && pNameNoExt.substr(pNameNoExt.size()-4) == ".exe")
                pNameNoExt = pNameNoExt.substr(0, pNameNoExt.size()-4);
            if (pName == lowerTarget || pNameNoExt == lowerNoExt) {
                pids.push_back(pe.th32ProcessID);
            }
        } while (Process32Next(hSnapshot, &pe));
    }
    CloseHandle(hSnapshot);
    return pids;
}

std::map<std::string, double> ProcessMonitor::GetMultiProcessCpuUsage(const std::vector<std::string>& processNames) {
    std::map<std::string, double> result;
    int numProcessors = 0;
    {
        SYSTEM_INFO sysInfo;
        GetSystemInfo(&sysInfo);
        numProcessors = sysInfo.dwNumberOfProcessors;
        if (numProcessors < 1) numProcessors = 1;
    }

    double now = TimeUtil::SecondsSinceEpoch();

    for (const auto& procName : processNames) {
        auto pids = GetProcessPids(procName);
        double totalCpuPercent = 0.0;

        for (unsigned long pid : pids) {
            HANDLE hProc = OpenProcess(PROCESS_QUERY_INFORMATION, FALSE, pid);
            if (!hProc) continue;

            FILETIME createTime, exitTime, kernelTime, userTime;
            if (GetProcessTimes(hProc, &createTime, &exitTime, &kernelTime, &userTime)) {
                ULARGE_INTEGER kernel, user;
                kernel.LowPart = kernelTime.dwLowDateTime;
                kernel.HighPart = kernelTime.dwHighDateTime;
                user.LowPart = userTime.dwLowDateTime;
                user.HighPart = userTime.dwHighDateTime;

                double kSec = kernel.QuadPart / 10000000.0;
                double uSec = user.QuadPart / 10000000.0;

                std::string key = procName + "_" + std::to_string(pid);
                std::lock_guard<std::mutex> lock(statesMutex_);
                auto& state = processStates_[key];
                if (state.lastWallTime > 0) {
                    double wallDelta = now - state.lastWallTime;
                    if (wallDelta > 0.05) {
                        double cpuDelta = (kSec - state.lastKernelTime) + (uSec - state.lastUserTime);
                        double percent = (cpuDelta / wallDelta) * 100.0 / numProcessors;
                        state.lastCpuPercent = std::min(percent, 100.0);
                    }
                }
                state.lastKernelTime = kSec;
                state.lastUserTime = uSec;
                state.lastWallTime = now;
                totalCpuPercent += state.lastCpuPercent;
            }
            CloseHandle(hProc);
        }
        result[procName] = std::min(totalCpuPercent, 100.0);
    }
    return result;
}

bool ProcessMonitor::IsProcessRunning(const std::string& processName) {
    HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnapshot == INVALID_HANDLE_VALUE) return false;

    PROCESSENTRY32 pe;
    pe.dwSize = sizeof(PROCESSENTRY32);
    bool found = false;

    if (Process32First(hSnapshot, &pe)) {
        do {
            std::string name(pe.szExeFile);
            if (processName == name) {
                found = true;
                break;
            }
        } while (Process32Next(hSnapshot, &pe));
    }
    CloseHandle(hSnapshot);
    return found;
}

// Linux Implementation
#elif defined(PLATFORM_LINUX)

std::vector<ProcessInfo> ProcessMonitor::ListRunningProcesses() {
    std::vector<ProcessInfo> processes;
    DIR* dir = opendir("/proc");
    if (!dir) return processes;

    struct dirent* entry;
    while ((entry = readdir(dir)) != nullptr) {
        // Only process numeric directories (PIDs)
        if (entry->d_type != DT_DIR) continue;
        bool isNumeric = true;
        for (const char* p = entry->d_name; *p; ++p) {
            if (*p < '0' || *p > '9') { isNumeric = false; break; }
        }
        if (!isNumeric) continue;

        std::string commPath = std::string("/proc/") + entry->d_name + "/comm";
        std::ifstream commFile(commPath);
        if (commFile.is_open()) {
            ProcessInfo info;
            info.pid = std::stoul(entry->d_name);
            std::getline(commFile, info.name);
            info.cpuPercent = 0.0;
            processes.push_back(info);
        }
    }
    closedir(dir);

    std::sort(processes.begin(), processes.end(),
        [](const ProcessInfo& a, const ProcessInfo& b) { return a.name < b.name; });
    processes.erase(
        std::unique(processes.begin(), processes.end(),
            [](const ProcessInfo& a, const ProcessInfo& b) { return a.name == b.name; }),
        processes.end());

    return processes;
}

std::string ProcessMonitor::GetActiveProcessName() {
#ifdef HAS_X11
    Display* display = XOpenDisplay(nullptr);
    if (!display) return "Unknown";

    Window focusWin;
    int revertTo;
    XGetInputFocus(display, &focusWin, &revertTo);

    if (focusWin == None || focusWin == PointerRoot) {
        XCloseDisplay(display);
        return "Unknown";
    }

    // Walk up to find top-level window with _NET_WM_PID
    Atom pidAtom = XInternAtom(display, "_NET_WM_PID", True);
    if (pidAtom == None) {
        XCloseDisplay(display);
        return "Unknown";
    }

    // Try the focused window and its parents
    Window current = focusWin;
    unsigned long pid = 0;
    for (int i = 0; i < 10 && current != None; ++i) {
        Atom actualType;
        int actualFormat;
        unsigned long nItems, bytesAfter;
        unsigned char* propValue = nullptr;

        if (XGetWindowProperty(display, current, pidAtom, 0, 1, False, XA_CARDINAL,
                &actualType, &actualFormat, &nItems, &bytesAfter, &propValue) == Success) {
            if (propValue && nItems > 0) {
                pid = *reinterpret_cast<unsigned long*>(propValue);
                XFree(propValue);
                break;
            }
            if (propValue) XFree(propValue);
        }

        Window parent, root;
        Window* children = nullptr;
        unsigned int nChildren;
        if (XQueryTree(display, current, &root, &parent, &children, &nChildren)) {
            if (children) XFree(children);
            if (parent == root) break;
            current = parent;
        } else break;
    }

    XCloseDisplay(display);

    if (pid > 0) {
        std::string commPath = "/proc/" + std::to_string(pid) + "/comm";
        std::ifstream commFile(commPath);
        std::string name;
        if (commFile.is_open() && std::getline(commFile, name)) {
            return name;
        }
    }
#endif
    return "Unknown";
}

std::string ProcessMonitor::GetActiveWindowTitle() {
#ifdef HAS_X11
    Display* display = XOpenDisplay(nullptr);
    if (!display) return "";

    Window focusWin;
    int revertTo;
    XGetInputFocus(display, &focusWin, &revertTo);
    if (focusWin == None || focusWin == PointerRoot) {
        XCloseDisplay(display);
        return "";
    }

    // Get _NET_WM_NAME or WM_NAME
    Atom netWmName = XInternAtom(display, "_NET_WM_NAME", True);
    Atom utf8 = XInternAtom(display, "UTF8_STRING", True);
    std::string title;

    // Walk up to top-level window
    Window current = focusWin;
    for (int i = 0; i < 10 && current != None; ++i) {
        Atom actualType;
        int actualFormat;
        unsigned long nItems, bytesAfter;
        unsigned char* propValue = nullptr;

        if (netWmName != None && utf8 != None &&
            XGetWindowProperty(display, current, netWmName, 0, 1024, False, utf8,
                &actualType, &actualFormat, &nItems, &bytesAfter, &propValue) == Success) {
            if (propValue && nItems > 0) {
                title = std::string(reinterpret_cast<char*>(propValue));
                XFree(propValue);
                break;
            }
            if (propValue) XFree(propValue);
        }

        // Try WM_NAME fallback
        char* wmName = nullptr;
        if (XFetchName(display, current, &wmName) && wmName) {
            title = std::string(wmName);
            XFree(wmName);
            break;
        }

        Window parent, root;
        Window* children = nullptr;
        unsigned int nChildren;
        if (XQueryTree(display, current, &root, &parent, &children, &nChildren)) {
            if (children) XFree(children);
            if (parent == root) break;
            current = parent;
        } else break;
    }

    XCloseDisplay(display);
    return title;
#else
    return "";
#endif
}

static long long lastTotalCpu = 0, lastIdleCpu = 0;
static bool cpuInitialized = false;

double ProcessMonitor::GetSystemCpuUsage() {
    std::ifstream statFile("/proc/stat");
    if (!statFile.is_open()) return 0.0;

    std::string line;
    std::getline(statFile, line);
    // Format: cpu user nice system idle iowait irq softirq
    std::istringstream iss(line);
    std::string cpu;
    long long user, nice, system, idle, iowait, irq, softirq, steal;
    iss >> cpu >> user >> nice >> system >> idle >> iowait >> irq >> softirq >> steal;

    long long totalIdle = idle + iowait;
    long long total = user + nice + system + idle + iowait + irq + softirq + steal;

    if (!cpuInitialized) {
        lastTotalCpu = total;
        lastIdleCpu = totalIdle;
        cpuInitialized = true;
        return 0.0;
    }

    long long totalDiff = total - lastTotalCpu;
    long long idleDiff = totalIdle - lastIdleCpu;
    lastTotalCpu = total;
    lastIdleCpu = totalIdle;

    if (totalDiff == 0) return 0.0;
    return (1.0 - (double)idleDiff / (double)totalDiff) * 100.0;
}

double ProcessMonitor::GetProcessCpuUsage(const std::string& processName) {
    auto result = GetMultiProcessCpuUsage({processName});
    auto it = result.find(processName);
    if (it != result.end()) return it->second;
    return 0.0;
}

std::vector<unsigned long> ProcessMonitor::GetProcessPids(const std::string& processName) {
    std::vector<unsigned long> pids;
    DIR* dir = opendir("/proc");
    if (!dir) return pids;

    std::string lowerTarget = processName;
    std::transform(lowerTarget.begin(), lowerTarget.end(), lowerTarget.begin(), ::tolower);
    if (lowerTarget.size() > 4 && lowerTarget.substr(lowerTarget.size()-4) == ".exe")
        lowerTarget = lowerTarget.substr(0, lowerTarget.size()-4);

    struct dirent* entry;
    while ((entry = readdir(dir)) != nullptr) {
        if (entry->d_type != DT_DIR) continue;
        bool isNumeric = true;
        for (const char* p = entry->d_name; *p; ++p) {
            if (*p < '0' || *p > '9') { isNumeric = false; break; }
        }
        if (!isNumeric) continue;

        std::string commPath = std::string("/proc/") + entry->d_name + "/comm";
        std::ifstream commFile(commPath);
        if (commFile.is_open()) {
            std::string name;
            std::getline(commFile, name);
            std::string lowerName = name;
            std::transform(lowerName.begin(), lowerName.end(), lowerName.begin(), ::tolower);
            if (lowerName == lowerTarget || lowerName == processName) {
                pids.push_back(std::stoul(entry->d_name));
            }
        }
    }
    closedir(dir);
    return pids;
}

std::map<std::string, double> ProcessMonitor::GetMultiProcessCpuUsage(const std::vector<std::string>& processNames) {
    std::map<std::string, double> result;
    long clkTck = sysconf(_SC_CLK_TCK);
    if (clkTck <= 0) clkTck = 100;
    long numCpus = sysconf(_SC_NPROCESSORS_ONLN);
    if (numCpus <= 0) numCpus = 1;
    double now = TimeUtil::SecondsSinceEpoch();

    for (const auto& procName : processNames) {
        auto pids = GetProcessPids(procName);
        double totalCpuPercent = 0.0;

        for (unsigned long pid : pids) {
            std::string statPath = "/proc/" + std::to_string(pid) + "/stat";
            std::ifstream statFile(statPath);
            if (!statFile.is_open()) continue;

            std::string line;
            std::getline(statFile, line);
            size_t commEnd = line.rfind(')');
            if (commEnd == std::string::npos) continue;
            std::istringstream iss(line.substr(commEnd + 2));
            std::string field;
            for (int i = 0; i < 11; i++) iss >> field;
            long long utime, stime;
            iss >> utime >> stime;

            double cpuTime = (utime + stime) / (double)clkTck;
            std::string key = procName + "_" + std::to_string(pid);
            std::lock_guard<std::mutex> lock(statesMutex_);
            auto& state = processStates_[key];
            if (state.lastWallTime > 0) {
                double wallDelta = now - state.lastWallTime;
                if (wallDelta > 0.05) {
                    double cpuDelta = cpuTime - state.lastKernelTime;
                    double percent = (cpuDelta / wallDelta) * 100.0 / numCpus;
                    state.lastCpuPercent = std::min(std::max(percent, 0.0), 100.0);
                }
            }
            state.lastKernelTime = cpuTime;
            state.lastWallTime = now;
            totalCpuPercent += state.lastCpuPercent;
        }
        result[procName] = std::min(totalCpuPercent, 100.0);
    }
    return result;
}

bool ProcessMonitor::IsProcessRunning(const std::string& processName) {
    DIR* dir = opendir("/proc");
    if (!dir) return false;

    struct dirent* entry;
    while ((entry = readdir(dir)) != nullptr) {
        if (entry->d_type != DT_DIR) continue;
        bool isNumeric = true;
        for (const char* p = entry->d_name; *p; ++p) {
            if (*p < '0' || *p > '9') { isNumeric = false; break; }
        }
        if (!isNumeric) continue;

        std::string commPath = std::string("/proc/") + entry->d_name + "/comm";
        std::ifstream commFile(commPath);
        if (commFile.is_open()) {
            std::string name;
            std::getline(commFile, name);
            if (name == processName) {
                closedir(dir);
                return true;
            }
        }
    }
    closedir(dir);
    return false;
}

// macOS Implementation
#elif defined(PLATFORM_MAC)

std::vector<ProcessInfo> ProcessMonitor::ListRunningProcesses() {
    std::vector<ProcessInfo> processes;

    // Use sysctl to get process list
    int mib[4] = { CTL_KERN, KERN_PROC, KERN_PROC_ALL, 0 };
    size_t size = 0;
    if (sysctl(mib, 4, nullptr, &size, nullptr, 0) < 0) return processes;

    std::vector<struct kinfo_proc> procList(size / sizeof(struct kinfo_proc));
    if (sysctl(mib, 4, procList.data(), &size, nullptr, 0) < 0) return processes;

    size_t count = size / sizeof(struct kinfo_proc);
    for (size_t i = 0; i < count; ++i) {
        ProcessInfo info;
        info.pid = procList[i].kp_proc.p_pid;
        info.name = std::string(procList[i].kp_proc.p_comm);
        info.cpuPercent = 0.0;
        processes.push_back(info);
    }

    std::sort(processes.begin(), processes.end(),
        [](const ProcessInfo& a, const ProcessInfo& b) { return a.name < b.name; });
    processes.erase(
        std::unique(processes.begin(), processes.end(),
            [](const ProcessInfo& a, const ProcessInfo& b) { return a.name == b.name; }),
        processes.end());

    return processes;
}

std::string ProcessMonitor::GetActiveProcessName() {
    // Use AppleScript via system command to get active app
    FILE* pipe = popen("osascript -e 'tell application \"System Events\" to get name of first application process whose frontmost is true' 2>/dev/null", "r");
    if (!pipe) return "Unknown";

    char buffer[256];
    std::string result;
    while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
        result += buffer;
    }
    pclose(pipe);

    while (!result.empty() && (result.back() == '\n' || result.back() == '\r'))
        result.pop_back();

    return result.empty() ? "Unknown" : result;
}

std::string ProcessMonitor::GetActiveWindowTitle() {
    FILE* pipe = popen("osascript -e 'tell application \"System Events\" to get title of front window of (first application process whose frontmost is true)' 2>/dev/null", "r");
    if (!pipe) return "";

    char buffer[512];
    std::string result;
    while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
        result += buffer;
    }
    pclose(pipe);

    while (!result.empty() && (result.back() == '\n' || result.back() == '\r'))
        result.pop_back();

    return result;
}

static processor_info_array_t lastCpuInfo = nullptr;
static mach_msg_type_number_t lastNumCpuInfo = 0;
static bool cpuInitialized = false;

double ProcessMonitor::GetSystemCpuUsage() {
    natural_t numCPUs = 0;
    processor_info_array_t cpuInfo;
    mach_msg_type_number_t numCpuInfo;

    kern_return_t kr = host_processor_info(mach_host_self(), PROCESSOR_CPU_LOAD_INFO,
                                            &numCPUs, &cpuInfo, &numCpuInfo);
    if (kr != KERN_SUCCESS) return 0.0;

    double totalUsage = 0.0;

    if (cpuInitialized && lastCpuInfo) {
        for (natural_t i = 0; i < numCPUs; ++i) {
            double inUse = (cpuInfo[(CPU_STATE_MAX * i) + CPU_STATE_USER] -
                           lastCpuInfo[(CPU_STATE_MAX * i) + CPU_STATE_USER]) +
                          (cpuInfo[(CPU_STATE_MAX * i) + CPU_STATE_SYSTEM] -
                           lastCpuInfo[(CPU_STATE_MAX * i) + CPU_STATE_SYSTEM]) +
                          (cpuInfo[(CPU_STATE_MAX * i) + CPU_STATE_NICE] -
                           lastCpuInfo[(CPU_STATE_MAX * i) + CPU_STATE_NICE]);
            double total = inUse +
                          (cpuInfo[(CPU_STATE_MAX * i) + CPU_STATE_IDLE] -
                           lastCpuInfo[(CPU_STATE_MAX * i) + CPU_STATE_IDLE]);
            if (total > 0) totalUsage += (inUse / total) * 100.0;
        }
        totalUsage /= numCPUs;
        vm_deallocate(mach_task_self(), (vm_address_t)lastCpuInfo,
                      sizeof(integer_t) * lastNumCpuInfo);
    }

    lastCpuInfo = cpuInfo;
    lastNumCpuInfo = numCpuInfo;
    cpuInitialized = true;

    return totalUsage;
}

double ProcessMonitor::GetProcessCpuUsage(const std::string& processName) {
    auto result = GetMultiProcessCpuUsage({processName});
    auto it = result.find(processName);
    if (it != result.end()) return it->second;
    return 0.0;
}

std::vector<unsigned long> ProcessMonitor::GetProcessPids(const std::string& processName) {
    std::vector<unsigned long> pids;
    std::string cmd = "pgrep -i -x '" + processName + "' 2>/dev/null";
    FILE* pipe = popen(cmd.c_str(), "r");
    if (!pipe) return pids;
    char buffer[64];
    while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
        try { pids.push_back(std::stoul(std::string(buffer))); } catch (...) {}
    }
    pclose(pipe);
    // Also try without .exe extension
    if (pids.empty() && processName.size() > 4) {
        std::string noExt = processName;
        std::transform(noExt.begin(), noExt.end(), noExt.begin(), ::tolower);
        if (noExt.substr(noExt.size()-4) == ".exe") {
            noExt = noExt.substr(0, noExt.size()-4);
            cmd = "pgrep -i -x '" + noExt + "' 2>/dev/null";
            pipe = popen(cmd.c_str(), "r");
            if (pipe) {
                while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
                    try { pids.push_back(std::stoul(std::string(buffer))); } catch (...) {}
                }
                pclose(pipe);
            }
        }
    }
    return pids;
}

std::map<std::string, double> ProcessMonitor::GetMultiProcessCpuUsage(const std::vector<std::string>& processNames) {
    std::map<std::string, double> result;
    // On macOS, use ps to get CPU percent
    for (const auto& procName : processNames) {
        auto pids = GetProcessPids(procName);
        double total = 0.0;
        for (unsigned long pid : pids) {
            std::string cmd = "ps -p " + std::to_string(pid) + " -o %cpu= 2>/dev/null";
            FILE* pipe = popen(cmd.c_str(), "r");
            if (pipe) {
                char buf[64];
                if (fgets(buf, sizeof(buf), pipe)) {
                    try { total += std::stod(std::string(buf)); } catch (...) {}
                }
                pclose(pipe);
            }
        }
        result[procName] = std::min(total, 100.0);
    }
    return result;
}

bool ProcessMonitor::IsProcessRunning(const std::string& processName) {
    std::string cmd = "pgrep -x '" + processName + "' > /dev/null 2>&1";
    return system(cmd.c_str()) == 0;
}

#endif
