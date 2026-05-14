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
};

class HardwareDetect {
public:
    static HardwareInfo DetectAll();

    static std::string DetectCpuName();
    static int DetectCpuCores();
    static int DetectCpuThreads();
    static double EstimateCpuTdp(const std::string& cpuName, int cores);

    static std::string DetectGpuName();
    static double EstimateGpuTdp(const std::string& gpuName);

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
