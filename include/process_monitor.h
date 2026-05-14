#pragma once
#include "platform.h"

// ============================================================
// Process Monitor - Detects running and active processes
// ============================================================

struct ProcessInfo {
    unsigned long pid;
    std::string name;
    double cpuPercent; // 0-100
};

// Per-process CPU tracking state
struct PerProcessCpuState {
    double lastKernelTime;
    double lastUserTime;
    double lastWallTime;
    double lastCpuPercent;
};

class ProcessMonitor {
public:
    // Get list of all running processes
    static std::vector<ProcessInfo> ListRunningProcesses();

    // Get the currently active (foreground) application name
    static std::string GetActiveProcessName();

    // Get the currently active window title (for browser tab detection)
    static std::string GetActiveWindowTitle();

    // Get CPU usage percentage for a given process name (0-100)
    static double GetProcessCpuUsage(const std::string& processName);

    // Returns map of processName -> cpuPercent (0-100)
    static std::map<std::string, double> GetMultiProcessCpuUsage(const std::vector<std::string>& processNames);

    // Get total system CPU usage percentage (0-100)
    static double GetSystemCpuUsage();

    // Check if a process with the given name is currently running
    static bool IsProcessRunning(const std::string& processName);

    // Get all PIDs for a given process name
    static std::vector<unsigned long> GetProcessPids(const std::string& processName);

private:
    static std::map<std::string, PerProcessCpuState> processStates_;
    static std::mutex statesMutex_;
};
