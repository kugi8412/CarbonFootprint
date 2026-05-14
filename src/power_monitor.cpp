#include "power_monitor.h"
#include "screen_monitor.h"

// ============================================================
// Power Monitor Implementation
// ============================================================

PowerMonitor::PowerMonitor(double cpuTdp, double gpuTdp, double basePower)
    : cpuTdpWatts_(cpuTdp), gpuTdpWatts_(gpuTdp), baseSystemWatts_(basePower),
      nvmlInitialized_(false), lastRaplEnergy_(0), lastRaplTime_(0) {

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
        std::cout << "[NVML] GPU not available, using power estimates.\n";
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

long long PowerMonitor::ReadRaplEnergyMicroJoules() {
#ifdef PLATFORM_LINUX
    std::ifstream file("/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj");
    if (file.is_open()) {
        long long energy;
        file >> energy;
        return energy;
    }
#endif
    return -1;
}

double PowerMonitor::GetCpuPower(double cpuUsagePercent) {
#ifdef PLATFORM_LINUX
    // Try Intel RAPL first
    long long currentEnergy = ReadRaplEnergyMicroJoules();
    double currentTime = TimeUtil::SecondsSinceEpoch();

    if (currentEnergy > 0 && lastRaplEnergy_ > 0 && lastRaplTime_ > 0) {
        double timeDelta = currentTime - lastRaplTime_;
        if (timeDelta > 0.1) {
            long long energyDelta = currentEnergy - lastRaplEnergy_;
            // Handle overflow (RAPL counter wraps around)
            if (energyDelta < 0) energyDelta += (1LL << 32);
            double watts = (energyDelta / 1000000.0) / timeDelta;
            lastRaplEnergy_ = currentEnergy;
            lastRaplTime_ = currentTime;
            return watts;
        }
    }
    lastRaplEnergy_ = currentEnergy;
    lastRaplTime_ = currentTime;
    if (currentEnergy > 0) return 0.0; // First reading, no delta yet
#endif

    // Estimate CPU power based on usage percentage and TDP
    // P = P_idle + (P_tdp - P_idle) * (usage / 100)^1.4
    // Non-linear because power scales super-linearly with frequency/voltage
    double idlePower = cpuTdpWatts_ * 0.1; // 10% of TDP at idle
    double usageFraction = std::min(cpuUsagePercent / 100.0, 1.0);
    return idlePower + (cpuTdpWatts_ - idlePower) * std::pow(usageFraction, 1.4);
}

double PowerMonitor::GetGpuPower() {
#ifdef HAS_NVML
    if (nvmlInitialized_) {
        unsigned int powerMilliWatts = 0;
        nvmlReturn_t result = nvmlDeviceGetPowerUsage(nvmlDevice_, &powerMilliWatts);
        if (result == NVML_SUCCESS) {
            return powerMilliWatts / 1000.0;
        }
    }
#endif

    // Estimate: GPU idles at ~10-20W, assume 15% of TDP at idle
    // Without monitoring, we estimate moderate usage
    double idlePower = gpuTdpWatts_ * 0.15;
    return idlePower; // Conservative idle estimate when no NVML
}

PowerReading PowerMonitor::GetCurrentPower(double cpuUsagePercent, double screenBrightness) {
    PowerReading r;
    r.cpuWatts = GetCpuPower(cpuUsagePercent);
    r.gpuWatts = GetGpuPower();
    r.screenWatts = ScreenMonitor::EstimateScreenPower(screenBrightness);
    r.otherWatts = baseSystemWatts_; // RAM, disks, fans, PSU inefficiency
    r.totalWatts = r.cpuWatts + r.gpuWatts + r.screenWatts + r.otherWatts;
    return r;
}
