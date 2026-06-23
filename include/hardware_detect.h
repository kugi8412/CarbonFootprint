#pragma once
#include "platform.h"

// ============================================================
// Hardware Detection - Auto-detect CPU/GPU/system specs
// ============================================================

struct HardwareInfo {
    std::string cpuName;
    double cpuTdpWatts;
    int cpuCores;
    int cpuThreads;

    std::string gpuName;
    double gpuTdpWatts;

    bool isLaptop;
    double baseSystemWatts;

    bool cpuDetected;
    bool gpuDetected;
    bool laptopDetected;

    // True when the TDP/power value was read directly from the device
    // (RAPL power cap / GPU driver) rather than estimated from a lookup table.
    bool cpuTdpMeasured;
    bool gpuTdpMeasured;
    bool isWsl;
};

class HardwareDetect {
public:
    static HardwareInfo DetectAll();

    static std::string DetectCpuName();
    static int DetectCpuCores();
    static int DetectCpuThreads();
    static double EstimateCpuTdp(const std::string& cpuName, int cores);
    // Reads the real CPU package power limit from Intel/AMD RAPL (Linux powercap).
    // Returns watts, or 0.0 when not available (Windows, macOS, most WSL setups).
    static double DetectCpuTdpFromDevice();

    static std::string DetectGpuName();
    static double EstimateGpuTdp(const std::string& gpuName);
    // Queries the real GPU board power limit from the driver (nvidia-smi / rocm-smi).
    // Works on Windows, Linux and WSL2. Returns watts, or 0.0 when unavailable.
    static double DetectGpuTdpFromDevice();

    // True when running under Windows Subsystem for Linux.
    static bool DetectIsWsl();
    static bool DetectIsLaptop();
    static double EstimateBasePower(bool isLaptop);

    static void PrintDetectedHardware(const HardwareInfo& info);

private:
    // CPU TDP lookup table
    struct CpuTdpEntry {
        const char* pattern;
        double tdpWatts;
    };
    static const std::vector<CpuTdpEntry>& GetCpuTdpTable();

    // GPU TDP lookup table
    struct GpuTdpEntry {
        const char* pattern;
        double tdpWatts;
    };
    static const std::vector<GpuTdpEntry>& GetGpuTdpTable();

    static bool ContainsIgnoreCase(const std::string& haystack, const std::string& needle);
};
