#include "carbon_engine.h"
#include "report.h"
#include "globals.h"

// ============================================================
// Carbon Footprint Engine Implementation
// ============================================================

CarbonEngine::CarbonEngine(const EngineConfig& config)
    : config_(config),
      powerMonitor_(config.cpuTdpWatts, config.gpuTdpWatts, config.baseSystemWatts),
      carbonApi_(config.zone, config.apiKey),
      running_(false),
      sessionStartTime_(0),
      totalSessionCarbonGrams_(0),
      totalSessionEnergyKwh_(0),
      totalSessionSeconds_(0) {
}

CarbonEngine::~CarbonEngine() {
    if (running_) {
        Stop();
    }
}

bool CarbonEngine::IsTargetApp(const std::string& appName) {
    for (const auto& target : config_.targetApps) {
        // Case-insensitive comparison
        std::string lower1 = appName;
        std::string lower2 = target;
        std::transform(lower1.begin(), lower1.end(), lower1.begin(), ::tolower);
        std::transform(lower2.begin(), lower2.end(), lower2.begin(), ::tolower);

        if (lower1 == lower2) return true;

        // Also check without .exe extension
        std::string noExt1 = lower1, noExt2 = lower2;
        auto stripExe = [](std::string& s) {
            if (s.size() > 4 && s.substr(s.size() - 4) == ".exe")
                s = s.substr(0, s.size() - 4);
        };
        stripExe(noExt1);
        stripExe(noExt2);
        if (noExt1 == noExt2) return true;
    }
    return false;
}

void CarbonEngine::MonitorLoop() {
    int tickCount = 0;

    while (running_) {
        std::string activeApp = ProcessMonitor::GetActiveProcessName();
        std::string windowTitle = ProcessMonitor::GetActiveWindowTitle();
        double systemCpuUsage = ProcessMonitor::GetSystemCpuUsage();
        double brightness = ScreenMonitor::GetBrightness();
        if (brightness < 0) brightness = 0.5; // Default

        // Get per-process CPU usage for all target apps
        std::vector<std::string> appsToTrack;
        {
            std::lock_guard<std::mutex> lock(dataMutex_);
            appsToTrack = config_.targetApps;
        }
        auto perAppCpu = ProcessMonitor::GetMultiProcessCpuUsage(appsToTrack);

        // Calculate total tracked CPU usage for proportional energy allocation
        double totalTrackedCpu = 0.0;
        for (const auto& [name, cpu] : perAppCpu) {
            totalTrackedCpu += cpu;
        }

        PowerReading power = powerMonitor_.GetCurrentPower(systemCpuUsage, brightness);
        CarbonIntensityData intensity = carbonApi_.GetIntensity();

        double timeHours = config_.updateIntervalSeconds / 3600.0;
        double totalEnergyKwh = (power.totalWatts / 1000.0) * timeHours;
        double totalCarbonGrams = totalEnergyKwh * intensity.intensity;

        int currentHour = TimeUtil::CurrentHour();

        {
            std::lock_guard<std::mutex> lock(dataMutex_);
            totalSessionSeconds_ += config_.updateIntervalSeconds;
            totalSessionEnergyKwh_ += totalEnergyKwh;
            totalSessionCarbonGrams_ += totalCarbonGrams;

            // Track brightness
            brightnessHistory_.push_back({TimeUtil::SecondsSinceEpoch(), brightness});

            // Allocate energy to each running target app based on their CPU usage
            for (const auto& target : config_.targetApps) {
                auto cpuIt = perAppCpu.find(target);
                double appCpuPercent = (cpuIt != perAppCpu.end()) ? cpuIt->second : 0.0;

                // Skip if app is not running
                if (appCpuPercent <= 0.0 && !ProcessMonitor::IsProcessRunning(target))
                    continue;

                // Check browser tab filter - only count if the right tab is active
                if (!MatchesBrowserTabFilter(target, windowTitle)) {
                    // Browser is running but wrong tab is active - attribute minimal energy
                    // (background tab uses ~5% of what foreground does)
                    if (IsTargetApp(activeApp)) {
                        // It's the foreground app but wrong tab - skip
                        continue;
                    }
                }

                // Calculate this app's share of energy
                // Use per-process CPU for proportional allocation
                double appEnergyKwh;
                double appCarbonGrams;

                if (totalTrackedCpu > 0.1) {
                    // Proportional allocation: app_energy = total_energy * (app_cpu / system_cpu)
                    double cpuShare = appCpuPercent / std::max(systemCpuUsage, 1.0);
                    cpuShare = std::min(cpuShare, 1.0);
                    appEnergyKwh = totalEnergyKwh * cpuShare;
                    appCarbonGrams = appEnergyKwh * intensity.intensity;
                } else if (IsTargetApp(activeApp)) {
                    // App is active (foreground) but low CPU - give it idle power share
                    double idleFraction = 0.1; // 10% of system power as minimum
                    appEnergyKwh = totalEnergyKwh * idleFraction;
                    appCarbonGrams = appEnergyKwh * intensity.intensity;
                } else {
                    // Running in background with near-zero CPU
                    double bgFraction = 0.02; // 2% background
                    appEnergyKwh = totalEnergyKwh * bgFraction;
                    appCarbonGrams = appEnergyKwh * intensity.intensity;
                }

                auto& app = appData_[target];
                app.appName = target;
                app.totalActiveSeconds += config_.updateIntervalSeconds;
                app.totalEnergyKwh += appEnergyKwh;
                app.totalCarbonGrams += appCarbonGrams;
                app.carbonByHour[currentHour] += appCarbonGrams;
                app.energyByHour[currentHour] += appEnergyKwh;
                app.sampleCount++;
                // Update CPU stats
                app.avgCpuPercent = ((app.avgCpuPercent * (app.sampleCount - 1)) + appCpuPercent) / app.sampleCount;
                app.peakCpuPercent = std::max(app.peakCpuPercent, appCpuPercent);
            }
        }

        // Print live status every 10 ticks
        tickCount++;
        if (tickCount % 10 == 0) {
            std::cout << "\r[" << TimeUtil::Now() << "] "
                      << "Active: " << activeApp
                      << " | CPU: " << std::fixed << std::setprecision(1) << systemCpuUsage << "%"
                      << " | Power: " << std::setprecision(1) << power.totalWatts << "W"
                      << " | CO2: " << std::setprecision(2) << totalSessionCarbonGrams_ << "g"
                      << " | Intensity: " << std::setprecision(0) << intensity.intensity << "g/kWh"
                      << "     " << std::flush;
        }

        std::this_thread::sleep_for(std::chrono::seconds(config_.updateIntervalSeconds));
    }
}

void CarbonEngine::ApiUpdateLoop() {
    // Initial fetch
    carbonApi_.FetchLatest();

    while (running_) {
        // Update every 15 minutes
        for (int i = 0; i < 900 && running_; ++i) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
        if (running_) {
            carbonApi_.FetchLatest();
        }
    }
}

void CarbonEngine::Start() {
    if (running_) return;

    running_ = true;
    sessionStartTime_ = TimeUtil::SecondsSinceEpoch();

    std::cout << "\n========================================\n";
    std::cout << "  Carbon Footprint Tracker - STARTED\n";
    std::cout << "========================================\n";
    std::cout << "Zone: " << config_.zone << "\n";
    std::cout << "Monitoring " << config_.targetApps.size() << " application(s):\n";
    for (const auto& app : config_.targetApps) {
        std::cout << "  - " << app << "\n";
    }
    std::cout << "Update interval: " << config_.updateIntervalSeconds << "s\n";
    std::cout << "Press Ctrl+C to stop and generate report.\n";
    std::cout << "========================================\n\n";

    // Start API update thread
    apiThread_ = std::thread(&CarbonEngine::ApiUpdateLoop, this);

    // Run monitor loop on main thread context (or spawn thread)
    monitorThread_ = std::thread(&CarbonEngine::MonitorLoop, this);
}

void CarbonEngine::Stop() {
    if (!running_) return;
    running_ = false;
    std::cout << "\n\nStopping Carbon Footprint Tracker...\n";

    if (monitorThread_.joinable()) monitorThread_.join();
    if (apiThread_.joinable()) apiThread_.join();
}

bool CarbonEngine::IsRunning() const {
    return running_;
}

std::map<std::string, AppUsageData> CarbonEngine::GetAppData() {
    std::lock_guard<std::mutex> lock(dataMutex_);
    return appData_;
}

double CarbonEngine::GetTotalCarbonGrams() {
    std::lock_guard<std::mutex> lock(dataMutex_);
    return totalSessionCarbonGrams_;
}

double CarbonEngine::GetTotalEnergyKwh() {
    std::lock_guard<std::mutex> lock(dataMutex_);
    return totalSessionEnergyKwh_;
}

double CarbonEngine::GetSessionDurationSeconds() {
    std::lock_guard<std::mutex> lock(dataMutex_);
    return totalSessionSeconds_;
}

double CarbonEngine::GetCurrentIntensity() {
    return carbonApi_.GetIntensity().intensity;
}

std::string CarbonEngine::GetSessionStartTime() {
    auto t = static_cast<time_t>(sessionStartTime_);
    std::tm tm_buf{};
#ifdef PLATFORM_WINDOWS
    localtime_s(&tm_buf, &t);
#else
    localtime_r(&t, &tm_buf);
#endif
    char buf[64];
    std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &tm_buf);
    return std::string(buf);
}

std::vector<std::pair<double, double>> CarbonEngine::GetBrightnessHistory() {
    std::lock_guard<std::mutex> lock(dataMutex_);
    return brightnessHistory_;
}

const EngineConfig& CarbonEngine::GetConfig() const {
    return config_;
}

// --- Dynamic app management ---

void CarbonEngine::AddApp(const std::string& appName) {
    std::lock_guard<std::mutex> lock(dataMutex_);
    // Check for duplicates (case-insensitive)
    std::string lowerNew = appName;
    std::transform(lowerNew.begin(), lowerNew.end(), lowerNew.begin(), ::tolower);

    for (const auto& existing : config_.targetApps) {
        std::string lowerEx = existing;
        std::transform(lowerEx.begin(), lowerEx.end(), lowerEx.begin(), ::tolower);
        if (lowerEx == lowerNew) return; // already exists
    }
    config_.targetApps.push_back(appName);
}

void CarbonEngine::RemoveApp(const std::string& appName) {
    std::lock_guard<std::mutex> lock(dataMutex_);
    std::string lowerRm = appName;
    std::transform(lowerRm.begin(), lowerRm.end(), lowerRm.begin(), ::tolower);

    config_.targetApps.erase(
        std::remove_if(config_.targetApps.begin(), config_.targetApps.end(),
            [&](const std::string& s) {
                std::string lower = s;
                std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
                return lower == lowerRm;
            }),
        config_.targetApps.end());

    // Mark existing data as inactive but KEEP it for the report
    for (auto& [name, data] : appData_) {
        std::string lowerName = name;
        std::transform(lowerName.begin(), lowerName.end(), lowerName.begin(), ::tolower);
        std::string lowerRmNoExt = lowerRm;
        if (lowerRmNoExt.size() > 4 && lowerRmNoExt.substr(lowerRmNoExt.size()-4) == ".exe")
            lowerRmNoExt = lowerRmNoExt.substr(0, lowerRmNoExt.size()-4);
        std::string lowerNameNoExt = lowerName;
        if (lowerNameNoExt.size() > 4 && lowerNameNoExt.substr(lowerNameNoExt.size()-4) == ".exe")
            lowerNameNoExt = lowerNameNoExt.substr(0, lowerNameNoExt.size()-4);

        if (lowerName == lowerRm || lowerNameNoExt == lowerRmNoExt) {
            data.isActive = false;
        }
    }
}

std::vector<std::string> CarbonEngine::GetActiveApps() {
    std::lock_guard<std::mutex> lock(dataMutex_);
    return config_.targetApps;
}

// --- Browser tab filter ---

bool CarbonEngine::MatchesBrowserTabFilter(const std::string& appName, const std::string& windowTitle) {
    // Check if this app has a tab filter configured
    std::string lowerApp = appName;
    std::transform(lowerApp.begin(), lowerApp.end(), lowerApp.begin(), ::tolower);
    // Strip .exe
    std::string lowerAppNoExt = lowerApp;
    if (lowerAppNoExt.size() > 4 && lowerAppNoExt.substr(lowerAppNoExt.size()-4) == ".exe")
        lowerAppNoExt = lowerAppNoExt.substr(0, lowerAppNoExt.size()-4);

    for (const auto& filter : config_.tabFilters) {
        if (!filter.enabled) continue;
        std::string lowerBrowser = filter.browserProcess;
        std::transform(lowerBrowser.begin(), lowerBrowser.end(), lowerBrowser.begin(), ::tolower);
        std::string lowerBrowserNoExt = lowerBrowser;
        if (lowerBrowserNoExt.size() > 4 && lowerBrowserNoExt.substr(lowerBrowserNoExt.size()-4) == ".exe")
            lowerBrowserNoExt = lowerBrowserNoExt.substr(0, lowerBrowserNoExt.size()-4);

        if (lowerApp == lowerBrowser || lowerAppNoExt == lowerBrowserNoExt) {
            // This app has a tab filter - check if current window title matches
            if (windowTitle.empty()) return false;
            std::string lowerTitle = windowTitle;
            std::transform(lowerTitle.begin(), lowerTitle.end(), lowerTitle.begin(), ::tolower);
            std::string lowerFilter = filter.titleFilter;
            std::transform(lowerFilter.begin(), lowerFilter.end(), lowerFilter.begin(), ::tolower);
            return lowerTitle.find(lowerFilter) != std::string::npos;
        }
    }
    // No filter for this app - always track
    return true;
}

void CarbonEngine::AddTabFilter(const BrowserTabFilter& filter) {
    std::lock_guard<std::mutex> lock(dataMutex_);
    // Replace existing filter for same browser
    for (auto& f : config_.tabFilters) {
        std::string l1 = f.browserProcess, l2 = filter.browserProcess;
        std::transform(l1.begin(), l1.end(), l1.begin(), ::tolower);
        std::transform(l2.begin(), l2.end(), l2.begin(), ::tolower);
        if (l1 == l2) {
            f = filter;
            return;
        }
    }
    config_.tabFilters.push_back(filter);
}

void CarbonEngine::RemoveTabFilter(const std::string& browserProcess) {
    std::lock_guard<std::mutex> lock(dataMutex_);
    std::string lower = browserProcess;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    config_.tabFilters.erase(
        std::remove_if(config_.tabFilters.begin(), config_.tabFilters.end(),
            [&](const BrowserTabFilter& f) {
                std::string l = f.browserProcess;
                std::transform(l.begin(), l.end(), l.begin(), ::tolower);
                return l == lower;
            }),
        config_.tabFilters.end());
}

std::vector<BrowserTabFilter> CarbonEngine::GetTabFilters() {
    std::lock_guard<std::mutex> lock(dataMutex_);
    return config_.tabFilters;
}

// --- Previous sessions & projection ---

void CarbonEngine::AddPreviousSession(const PreviousSession& session) {
    std::lock_guard<std::mutex> lock(dataMutex_);
    previousSessions_.push_back(session);
}

std::vector<PreviousSession> CarbonEngine::GetPreviousSessions() {
    std::lock_guard<std::mutex> lock(dataMutex_);
    return previousSessions_;
}

CarbonEngine::Projection CarbonEngine::ProjectFuture(double futureHours) {
    std::lock_guard<std::mutex> lock(dataMutex_);
    Projection proj{};
    proj.projectedHours = futureHours;

    // Current session rate
    double sessionHours = totalSessionSeconds_ / 3600.0;
    if (sessionHours > 0.001) {
        proj.currentSessionRate = totalSessionCarbonGrams_ / sessionHours;
        proj.avgEnergyPerHour = totalSessionEnergyKwh_ / sessionHours;
    }

    // Historical rate from previous sessions
    double totalHistCarbon = 0;
    double totalHistHours = 0;
    double totalHistEnergy = 0;
    for (const auto& s : previousSessions_) {
        totalHistCarbon += s.carbonGrams;
        totalHistHours += s.durationSeconds / 3600.0;
        totalHistEnergy += s.energyKwh;
    }
    if (totalHistHours > 0.001) {
        proj.historicalRate = totalHistCarbon / totalHistHours;
    }

    // Combined weighted average (current session weighted more if substantial)
    double combinedCarbon = totalSessionCarbonGrams_ + totalHistCarbon;
    double combinedHours = sessionHours + totalHistHours;
    double combinedEnergy = totalSessionEnergyKwh_ + totalHistEnergy;

    if (combinedHours > 0.001) {
        proj.avgCarbonPerHour = combinedCarbon / combinedHours;
        proj.avgEnergyPerHour = combinedEnergy / combinedHours;
    } else {
        // No data at all, estimate from current power draw
        CarbonIntensityData intensity = carbonApi_.GetIntensity();
        double estimatedWatts = 100.0;
        proj.avgEnergyPerHour = estimatedWatts / 1000.0;
        proj.avgCarbonPerHour = proj.avgEnergyPerHour * intensity.intensity;
    }

    proj.projectedCarbonGrams = proj.avgCarbonPerHour * futureHours;
    proj.projectedEnergyKwh = proj.avgEnergyPerHour * futureHours;
    proj.totalDataSessions = static_cast<int>(previousSessions_.size()) + (sessionHours > 0.001 ? 1 : 0);

    return proj;
}
