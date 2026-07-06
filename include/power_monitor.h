#pragma once
#include "platform.h"

// ============================================================
// Power Monitor - Measured + estimated system power consumption
// ============================================================

struct PowerReading {
    double cpuWatts = 0.0;
    double gpuWatts = 0.0;
    double screenWatts = 0.0;
    double otherWatts = 0.0;  // RAM, disks, fans, etc.
    double totalWatts = 0.0;

    // Provenance of each figure: true when read from a real sensor,
    // false when derived from a TDP model.
    bool cpuMeasured = false;
    bool gpuMeasured = false;
    bool systemMeasured = false;    // whole-system draw from the battery

    std::string cpuSource = "estimate";   // rapl | sensor | lhm-http | estimate
    std::string gpuSource = "estimate";   // nvml | nvidia-smi | lhm-http | estimate
    std::string systemSource;             // battery | (empty)
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

    // --- Intel/AMD RAPL (Linux) ---
    long long ReadRaplEnergyMicroJoules();   // sums all package domains
    double lastRaplEnergy_;
    double lastRaplTime_;

    // --- Measured-power helpers ---
    // CPU package power from a real sensor (RAPL / LibreHardwareMonitor).
    double ReadMeasuredCpuPower(std::string& source);
    // GPU board power from a real sensor (NVML / nvidia-smi / LHM).
    double ReadMeasuredGpuPower(std::string& source);
    // Whole-system discharge power from the battery, or -1.0 when unavailable.
    double ReadSystemBatteryPower();
    // CPU package power (W) from a LibreHardwareMonitor/OpenHardwareMonitor
    // WMI sensor provider (Windows), or -1.0.
    double ReadWindowsSensorCpuPower();

    // TDP-model fallbacks.
    double EstimateCpuPower(double cpuUsagePercent);
    double EstimateGpuPower();

    // --- Caches so repeated measurements stay cheap ---
    double lastBatteryTime_;
    double lastBatteryWatts_;
    double lastSensorProbeTime_;   // last time the WMI sensor was searched
    bool   sensorAvailable_;       // an LHM/OHM WMI provider was found
    std::string sensorNamespace_;  // cached WMI namespace

public:
    PowerMonitor(double cpuTdp = 65.0, double gpuTdp = 150.0, double basePower = 30.0);
    ~PowerMonitor();

    // Get current power reading with breakdown and measured/estimated flags.
    PowerReading GetCurrentPower(double cpuUsagePercent, double screenBrightness);

    // Get GPU power via NVML/nvidia-smi/LHM if available, otherwise estimate.
    double GetGpuPower(std::string* source = nullptr);

    // Get CPU power via RAPL/LHM if available, otherwise estimate.
    double GetCpuPower(double cpuUsagePercent, std::string* source = nullptr);
};
