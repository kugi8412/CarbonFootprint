#include "power_monitor.h"
#include "screen_monitor.h"

#include <cstdio>
#include <cstdlib>

// ============================================================
// Power Monitor Implementation
//
// Power is *measured* whenever the hardware exposes a real sensor and
// falls back to a TDP model otherwise. Measured sources, in order:
//   - CPU package: Intel/AMD RAPL (Linux) or a LibreHardwareMonitor /
//                  OpenHardwareMonitor WMI sensor (Windows).
//   - GPU board:   NVML, else `nvidia-smi power.draw`.
//   - Whole system: the battery discharge rate on laptops (all OSes),
//                   which is the true end-to-end draw and supersedes the
//                   component model when available.
// ============================================================

// --- Portable subprocess helpers -------------------------------------------
#ifdef PLATFORM_WINDOWS
    #define CF_POPEN  _popen
    #define CF_PCLOSE _pclose
    static const char* CF_NULLSINK = " 2>NUL";
#else
    #define CF_POPEN  popen
    #define CF_PCLOSE pclose
    static const char* CF_NULLSINK = " 2>/dev/null";
#endif

// Run a shell command and capture its stdout. Returns false on failure.
static bool CF_RunCommand(const std::string& cmd, std::string& out) {
    out.clear();
    FILE* pipe = CF_POPEN(cmd.c_str(), "r");
    if (!pipe) return false;
    char buf[256];
    while (std::fgets(buf, sizeof(buf), pipe) != nullptr) {
        out += buf;
    }
    CF_PCLOSE(pipe);
    return !out.empty();
}

// Parse the first numeric token (optionally comma/space separated) from text.
// Returns -1.0 when nothing parseable is found.
static double CF_ParseFirstDouble(const std::string& text) {
    std::istringstream iss(text);
    std::string line;
    while (std::getline(iss, line)) {
        size_t a = line.find_first_not_of(" \t\r\n");
        if (a == std::string::npos) continue;
        std::string token = line.substr(a);
        size_t c = token.find(',');
        if (c != std::string::npos) token = token.substr(0, c);
        char* end = nullptr;
        double v = std::strtod(token.c_str(), &end);
        if (end != token.c_str()) return v;
    }
    return -1.0;
}

#ifdef PLATFORM_LINUX
// Whole-system discharge power (W) from /sys/class/power_supply while a
// battery is actually discharging. Returns -1.0 when unavailable / on AC.
static double CF_ReadLinuxBatteryPower() {
    const char* base = "/sys/class/power_supply";
    DIR* dir = opendir(base);
    if (!dir) return -1.0;

    double result = -1.0;
    struct dirent* ent;
    while ((ent = readdir(dir)) != nullptr) {
        std::string name = ent->d_name;
        if (name == "." || name == "..") continue;
        std::string dev = std::string(base) + "/" + name;

        std::ifstream tf(dev + "/type");
        std::string kind;
        if (!(tf >> kind) || kind != "Battery") continue;

        std::ifstream sf(dev + "/status");
        std::string state;
        if (sf >> state && state != "Discharging") continue;

        // Preferred: power_now (microwatts).
        std::ifstream pf(dev + "/power_now");
        long long microWatts = 0;
        if (pf >> microWatts && microWatts != 0) {
            result = std::abs((double)microWatts) / 1e6;
            break;
        }
        // Otherwise derive from current (uA) and voltage (uV).
        std::ifstream cf(dev + "/current_now");
        std::ifstream vf(dev + "/voltage_now");
        long long microAmps = 0, microVolts = 0;
        if ((cf >> microAmps) && (vf >> microVolts) && microAmps != 0) {
            double watts = (std::abs((double)microAmps) / 1e6) *
                           (std::abs((double)microVolts) / 1e6);
            if (watts > 0) { result = watts; break; }
        }
    }
    closedir(dir);
    return result;
}
#endif

// ============================================================

PowerMonitor::PowerMonitor(double cpuTdp, double gpuTdp, double basePower)
    : cpuTdpWatts_(cpuTdp), gpuTdpWatts_(gpuTdp), baseSystemWatts_(basePower),
      nvmlInitialized_(false), lastRaplEnergy_(0), lastRaplTime_(0),
      lastBatteryTime_(0), lastBatteryWatts_(-1.0),
      lastSensorProbeTime_(0), sensorAvailable_(false) {

#ifdef HAS_NVML
    nvmlReturn_t result = nvmlInit();
    if (result == NVML_SUCCESS) {
        result = nvmlDeviceGetHandleByIndex(0, &nvmlDevice_);
        if (result == NVML_SUCCESS) {
            nvmlInitialized_ = true;
            std::cout << "[NVML] GPU power monitoring initialized.\n";
        }
    }
    if (!nvmlInitialized_) {
        std::cout << "[NVML] GPU not available, using nvidia-smi / estimates.\n";
    }
#endif
}

PowerMonitor::~PowerMonitor() {
#ifdef HAS_NVML
    if (nvmlInitialized_) {
        nvmlShutdown();
    }
#endif
}

// Sum the cumulative energy counter (uJ) across every top-level RAPL package.
long long PowerMonitor::ReadRaplEnergyMicroJoules() {
#ifdef PLATFORM_LINUX
    const char* base = "/sys/class/powercap";
    DIR* dir = opendir(base);
    if (dir) {
        long long total = 0;
        bool found = false;
        struct dirent* ent;
        while ((ent = readdir(dir)) != nullptr) {
            std::string name = ent->d_name;
            // Top-level package domains look like "intel-rapl:0" (one colon),
            // not subzones such as "intel-rapl:0:0".
            if (name.rfind("intel-rapl:", 0) != 0) continue;
            if (std::count(name.begin(), name.end(), ':') != 1) continue;
            std::ifstream f(std::string(base) + "/" + name + "/energy_uj");
            long long e = 0;
            if (f >> e) { total += e; found = true; }
        }
        closedir(dir);
        if (found) return total;
    }
    // Fallback to the classic single-package path.
    std::ifstream file("/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj");
    if (file.is_open()) {
        long long energy = 0;
        if (file >> energy) return energy;
    }
#endif
    return -1;
}

double PowerMonitor::ReadWindowsSensorCpuPower() {
#ifdef PLATFORM_WINDOWS
    auto query = [&](const std::string& ns) -> double {
        std::string cmd =
            "powershell.exe -NoProfile -Command \""
            "Get-CimInstance -Namespace " + ns + " -ClassName Sensor "
            "-ErrorAction SilentlyContinue | Where-Object { "
            "$_.SensorType -eq 'Power' -and $_.Name -match 'Package' } | "
            "Sort-Object Value -Descending | "
            "Select-Object -First 1 -ExpandProperty Value\"";
        std::string out;
        if (!CF_RunCommand(cmd, out)) return -1.0;
        double w = CF_ParseFirstDouble(out);
        return (w > 0) ? w : -1.0;
    };

    double now = TimeUtil::SecondsSinceEpoch();

    // Fast path: query the namespace we already found.
    if (sensorAvailable_ && !sensorNamespace_.empty()) {
        double w = query(sensorNamespace_);
        if (w > 0) return w;
        sensorAvailable_ = false;
        sensorNamespace_.clear();
    }

    // The full probe spawns PowerShell, so throttle it heavily when absent.
    if (lastSensorProbeTime_ > 0 && (now - lastSensorProbeTime_) < 300.0) {
        return -1.0;
    }
    lastSensorProbeTime_ = now;

    const char* namespaces[] = {"root/LibreHardwareMonitor", "root/OpenHardwareMonitor"};
    for (const char* ns : namespaces) {
        double w = query(ns);
        if (w > 0) {
            sensorAvailable_ = true;
            sensorNamespace_ = ns;
            return w;
        }
    }
#endif
    return -1.0;
}

double PowerMonitor::ReadMeasuredCpuPower(std::string& source) {
#ifdef PLATFORM_LINUX
    long long currentEnergy = ReadRaplEnergyMicroJoules();
    double currentTime = TimeUtil::SecondsSinceEpoch();
    if (currentEnergy > 0 && lastRaplEnergy_ > 0 && lastRaplTime_ > 0) {
        double timeDelta = currentTime - lastRaplTime_;
        if (timeDelta > 0.05) {
            long long energyDelta = currentEnergy - (long long)lastRaplEnergy_;
            if (energyDelta < 0) energyDelta += (1LL << 32);  // counter wrap
            double watts = (energyDelta / 1000000.0) / timeDelta;
            lastRaplEnergy_ = (double)currentEnergy;
            lastRaplTime_ = currentTime;
            if (watts > 0) { source = "rapl"; return watts; }
        }
    }
    if (currentEnergy > 0) {
        lastRaplEnergy_ = (double)currentEnergy;
        lastRaplTime_ = currentTime;
    }
#endif
#ifdef PLATFORM_WINDOWS
    double sensor = ReadWindowsSensorCpuPower();
    if (sensor > 0) { source = "sensor"; return sensor; }
#endif
    return -1.0;
}

double PowerMonitor::ReadMeasuredGpuPower(std::string& source) {
#ifdef HAS_NVML
    if (nvmlInitialized_) {
        unsigned int powerMilliWatts = 0;
        if (nvmlDeviceGetPowerUsage(nvmlDevice_, &powerMilliWatts) == NVML_SUCCESS
                && powerMilliWatts > 0) {
            source = "nvml";
            return powerMilliWatts / 1000.0;
        }
    }
#endif
    // nvidia-smi works even without an NVML build (driver ships it).
    std::string out;
    std::string cmd =
        std::string("nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits")
        + CF_NULLSINK;
    if (CF_RunCommand(cmd, out)) {
        double w = CF_ParseFirstDouble(out);
        if (w > 0) { source = "nvidia-smi"; return w; }
    }
    return -1.0;
}

double PowerMonitor::ReadSystemBatteryPower() {
    double now = TimeUtil::SecondsSinceEpoch();
    if (lastBatteryTime_ > 0 && (now - lastBatteryTime_) < 2.0) {
        return lastBatteryWatts_;
    }

    double watts = -1.0;

#ifdef PLATFORM_LINUX
    watts = CF_ReadLinuxBatteryPower();
#elif defined(PLATFORM_WINDOWS)
    // Only consult WMI when the machine is actually on battery.
    SYSTEM_POWER_STATUS sps;
    if (GetSystemPowerStatus(&sps) && sps.ACLineStatus == 0) {
        std::string cmd =
            "powershell.exe -NoProfile -Command \""
            "$b = Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus "
            "-ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if ($b -and $b.Discharging) { $b.DischargeRate } else { 0 }\"";
        std::string out;
        if (CF_RunCommand(cmd, out)) {
            double milliWatts = CF_ParseFirstDouble(out);
            if (milliWatts > 0) watts = milliWatts / 1000.0;
        }
    }
#elif defined(PLATFORM_MAC)
    std::string out;
    if (CF_RunCommand(std::string("ioreg -rn AppleSmartBattery") + CF_NULLSINK, out)) {
        long long amperage = 0, voltage = 0;  // mA (neg=discharge), mV
        bool haveA = false, haveV = false;
        std::istringstream iss(out);
        std::string line;
        while (std::getline(iss, line)) {
            if (line.find("\"Amperage\"") != std::string::npos) {
                size_t eq = line.rfind('=');
                if (eq != std::string::npos) { amperage = std::strtoll(line.c_str() + eq + 1, nullptr, 10); haveA = true; }
            } else if (line.find("\"Voltage\"") != std::string::npos) {
                size_t eq = line.rfind('=');
                if (eq != std::string::npos) { voltage = std::strtoll(line.c_str() + eq + 1, nullptr, 10); haveV = true; }
            }
        }
        if (haveA && haveV && amperage < 0) {
            double w = (std::abs((double)amperage) / 1000.0) * ((double)voltage / 1000.0);
            if (w > 0) watts = w;
        }
    }
#endif

    lastBatteryTime_ = now;
    lastBatteryWatts_ = watts;
    return watts;
}

double PowerMonitor::EstimateCpuPower(double cpuUsagePercent) {
    // P = P_idle + (P_tdp - P_idle) * (usage/100)^1.4
    // Non-linear because power scales super-linearly with frequency/voltage.
    double idlePower = cpuTdpWatts_ * 0.1;  // ~10% of TDP at idle
    double usageFraction = std::min(cpuUsagePercent / 100.0, 1.0);
    return idlePower + (cpuTdpWatts_ - idlePower) * std::pow(usageFraction, 1.4);
}

double PowerMonitor::EstimateGpuPower() {
    // Conservative idle estimate when no sensor is available (~15% of TDP).
    return gpuTdpWatts_ * 0.15;
}

double PowerMonitor::GetCpuPower(double cpuUsagePercent, std::string* source) {
    std::string src;
    double measured = ReadMeasuredCpuPower(src);
    if (measured > 0) {
        if (source) *source = src;
        return measured;
    }
    if (source) *source = "estimate";
    return EstimateCpuPower(cpuUsagePercent);
}

double PowerMonitor::GetGpuPower(std::string* source) {
    std::string src;
    double measured = ReadMeasuredGpuPower(src);
    if (measured > 0) {
        if (source) *source = src;
        return measured;
    }
    if (source) *source = "estimate";
    return EstimateGpuPower();
}

PowerReading PowerMonitor::GetCurrentPower(double cpuUsagePercent, double screenBrightness) {
    PowerReading r;

    std::string cpuSrc = "estimate", gpuSrc = "estimate";
    r.cpuWatts = GetCpuPower(cpuUsagePercent, &cpuSrc);
    r.gpuWatts = GetGpuPower(&gpuSrc);
    r.cpuSource = cpuSrc;
    r.gpuSource = gpuSrc;
    r.cpuMeasured = (cpuSrc != "estimate");
    r.gpuMeasured = (gpuSrc != "estimate");

    r.screenWatts = ScreenMonitor::EstimateScreenPower(screenBrightness);
    r.otherWatts = baseSystemWatts_;  // RAM, disks, fans, PSU inefficiency
    r.totalWatts = r.cpuWatts + r.gpuWatts + r.screenWatts + r.otherWatts;

    // A discharging battery reports the true whole-system draw; when present it
    // supersedes the summed component model.
    double systemWatts = ReadSystemBatteryPower();
    if (systemWatts > 0) {
        r.systemMeasured = true;
        r.systemSource = "battery";
        r.totalWatts = systemWatts;
    }

    return r;
}
