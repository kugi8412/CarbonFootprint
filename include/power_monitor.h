#pragma once
#include "platform.h"

// ============================================================
// Power Monitor - Estimates system power consumption
// ============================================================

struct PowerReading {
    double cpuWatts;
    double gpuWatts;
    double screenWatts;
    double otherWatts;  // RAM, disks, fans, etc.
    double totalWatts;
};

class PowerMonitor {
private:
    double cpuTdpWatts_;       // Configurable CPU TDP
    double gpuTdpWatts_;       // Configurable GPU TDP
    double baseSystemWatts_;   // Base system power (idle)
    bool nvmlInitialized_;

#ifdef HAS_NVML
    nvmlDevice_t nvmlDevice_;
#endif

    // Intel RAPL reading (Linux)
    long long ReadRaplEnergyMicroJoules();
    double lastRaplEnergy_;
    double lastRaplTime_;

public:
    PowerMonitor(double cpuTdp = 65.0, double gpuTdp = 150.0, double basePower = 30.0);
    ~PowerMonitor();

    // Get current power reading with breakdown
    PowerReading GetCurrentPower(double cpuUsagePercent, double screenBrightness);

    // Get GPU power via NVML if available, otherwise estimate
    double GetGpuPower();

    // Get CPU power via RAPL if available, otherwise estimate
    double GetCpuPower(double cpuUsagePercent);
};
