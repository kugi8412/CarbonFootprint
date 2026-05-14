#pragma once
#include "platform.h"
#include "process_monitor.h"
#include "power_monitor.h"
#include "screen_monitor.h"
#include "carbon_api.h"

// ============================================================
// Carbon Footprint Engine - Main tracking logic
// ============================================================

struct AppUsageData {
    std::string appName;
    double totalActiveSeconds;
    double totalEnergyKwh;
    double totalCarbonGrams;
    double avgCpuPercent;         // average CPU usage for this app
    double peakCpuPercent;        // peak CPU usage observed
    std::map<int, double> carbonByHour; // hour (0-23) -> grams CO2
    std::map<int, double> energyByHour; // hour (0-23) -> kWh
    bool isActive;  // true if currently being monitored
    int sampleCount;

    AppUsageData() : totalActiveSeconds(0), totalEnergyKwh(0),
                     totalCarbonGrams(0), avgCpuPercent(0), peakCpuPercent(0),
                     isActive(true), sampleCount(0) {}
};

// Browser tab filter - track only specific tabs/titles
struct BrowserTabFilter {
    std::string browserProcess;   // "firefox.exe", "chrome.exe"
    std::string titleFilter;      // substring to match in window title
    bool enabled;

    BrowserTabFilter() : enabled(false) {}
    BrowserTabFilter(const std::string& browser, const std::string& filter)
        : browserProcess(browser), titleFilter(filter), enabled(true) {}
};

// Previous session data for import/projection
struct PreviousSession {
    std::string description;
    double durationSeconds;
    double energyKwh;
    double carbonGrams;
    double avgIntensity;         // gCO2/kWh
    std::map<std::string, double> appCarbonGrams; // per-app breakdown
};

struct EngineConfig {
    std::vector<std::string> targetApps;
    std::vector<BrowserTabFilter> tabFilters;  // browser tab filters
    std::string zone;
    std::string apiKey;
    int updateIntervalSeconds;
    double cpuTdpWatts;
    double gpuTdpWatts;
    double baseSystemWatts;
    bool isLaptop;
    bool autoDetectedHardware;  // true if hardware was auto-detected
};

class CarbonEngine {
private:
    EngineConfig config_;
    ProcessMonitor processMonitor_;
    PowerMonitor powerMonitor_;
    CarbonAPI carbonApi_;

    std::map<std::string, AppUsageData> appData_;
    std::mutex dataMutex_;
    std::atomic<bool> running_;
    std::atomic<bool> inputReady_;  // signals new user input available
    std::thread monitorThread_;
    std::thread apiThread_;

    double sessionStartTime_;
    double totalSessionCarbonGrams_;
    double totalSessionEnergyKwh_;
    double totalSessionSeconds_;

    // Previous sessions for projection
    std::vector<PreviousSession> previousSessions_;

    // Brightness history for reporting
    std::vector<std::pair<double, double>> brightnessHistory_; // time, brightness

    bool IsTargetApp(const std::string& appName);
    bool MatchesBrowserTabFilter(const std::string& appName, const std::string& windowTitle);
    void MonitorLoop();
    void ApiUpdateLoop();

public:
    CarbonEngine(const EngineConfig& config);
    ~CarbonEngine();

    // Start monitoring
    void Start();

    // Stop monitoring
    void Stop();

    // Check if running
    bool IsRunning() const;

    // Get snapshot of all tracking data (thread-safe)
    std::map<std::string, AppUsageData> GetAppData();

    // Get session summary values
    double GetTotalCarbonGrams();
    double GetTotalEnergyKwh();
    double GetSessionDurationSeconds();
    double GetCurrentIntensity();
    std::string GetSessionStartTime();

    // Get brightness history
    std::vector<std::pair<double, double>> GetBrightnessHistory();

    // Get config
    const EngineConfig& GetConfig() const;

    // Dynamic app management
    void AddApp(const std::string& appName);
    void RemoveApp(const std::string& appName);
    std::vector<std::string> GetActiveApps();

    // Browser tab filter management
    void AddTabFilter(const BrowserTabFilter& filter);
    void RemoveTabFilter(const std::string& browserProcess);
    std::vector<BrowserTabFilter> GetTabFilters();

    // Previous sessions & projection
    void AddPreviousSession(const PreviousSession& session);
    std::vector<PreviousSession> GetPreviousSessions();

    // Project future carbon footprint based on current + historical data
    // futureHours: how many hours into the future to project
    struct Projection {
        double projectedCarbonGrams;
        double projectedEnergyKwh;
        double projectedHours;
        double avgCarbonPerHour;       // from all data (current + historical)
        double avgEnergyPerHour;
        double currentSessionRate;     // g CO2 per hour in this session
        double historicalRate;         // g CO2 per hour from previous sessions
        int totalDataSessions;
    };
    Projection ProjectFuture(double futureHours);
};
