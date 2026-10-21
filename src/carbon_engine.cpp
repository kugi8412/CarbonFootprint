#include "carbon_engine.h"
#include "report.h"
#include "globals.h"
#include <cctype>

// ============================================================
// Carbon Footprint Engine Implementation
// ============================================================

std::string AppKey(const std::string& name) {
    std::string key = name;
    // unsigned char: std::tolower on negative chars is undefined
    std::transform(key.begin(), key.end(), key.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (key.size() > 4 && key.compare(key.size() - 4, 4, ".exe") == 0)
        key.resize(key.size() - 4);
    return key;
}

static std::string LowerCopy(const std::string& s) {
    std::string out = s;
    std::transform(out.begin(), out.end(), out.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return out;
}

CarbonEngine::CarbonEngine(const EngineConfig& config)
    : config_(config),
      powerMonitor_(config.cpuTdpWatts, config.gpuTdpWatts, config.baseSystemWatts,
                    config.isLaptop),
      carbonApi_(config.zone, config.apiKey),
      running_(false),
      sessionStartTime_(0),
      totalSessionCarbonGrams_(0),
      totalSessionEnergyKwh_(0),
      totalSessionSeconds_(0) {
    // One entry per process name ("Slack.exe" == "slack")
    std::vector<std::string> unique;
    for (const auto& app : config_.targetApps) {
        bool dup = false;
        for (const auto& u : unique) dup = dup || AppKey(u) == AppKey(app);
        if (!dup && !app.empty()) unique.push_back(app);
    }
    config_.targetApps = unique;
}

CarbonEngine::~CarbonEngine() {
    // Joins the threads even after RequestStop()
    Stop();
}

bool CarbonEngine::IsTargetApp(const std::string& appName) {
    for (const auto& target : config_.targetApps) {
        if (AppKey(appName) == AppKey(target)) return true;
    }
    return false;
}

void CarbonEngine::MonitorLoop() {
    int tickCount = 0;
    auto lastTick = std::chrono::steady_clock::now();
    // Brightness is a PowerShell call on Windows; read it every 30 s
    double brightness = 0.5;
    auto lastBrightnessRead = lastTick - std::chrono::hours(1);

    while (running_) {
        std::string activeApp = ProcessMonitor::GetActiveProcessName();
        std::string windowTitle = ProcessMonitor::GetActiveWindowTitle();
        double systemCpuUsage = std::max(ProcessMonitor::GetSystemCpuUsage(), 0.0);
        if (std::chrono::steady_clock::now() - lastBrightnessRead >= std::chrono::seconds(30)) {
            brightness = ScreenMonitor::GetBrightness();
            if (brightness < 0) brightness = 0.5; // Default
            lastBrightnessRead = std::chrono::steady_clock::now();
        }

        // Get per-process CPU usage for all target apps
        std::vector<std::string> appsToTrack;
        {
            std::lock_guard<std::mutex> lock(dataMutex_);
            appsToTrack = config_.targetApps;
        }
        auto perAppCpu = ProcessMonitor::GetMultiProcessCpuUsage(appsToTrack);

        // Calculate total tracked CPU usage for proportional energy allocation
        double totalTrackedCpu = 0.0;
        for (auto& [name, cpu] : perAppCpu) {
            cpu = std::max(cpu, 0.0);
            totalTrackedCpu += cpu;
        }

        PowerReading power = powerMonitor_.GetCurrentPower(systemCpuUsage, brightness);
        CarbonIntensityData intensity = carbonApi_.GetIntensity();

        // Integrate over the real elapsed time; a long gap (sleep) counts as
        // one interval
        auto now = std::chrono::steady_clock::now();
        double dtSeconds = std::chrono::duration<double>(now - lastTick).count();
        lastTick = now;
        if (dtSeconds <= 0.0 ||
            dtSeconds > std::max(60.0, 5.0 * config_.updateIntervalSeconds)) {
            dtSeconds = config_.updateIntervalSeconds;
        }

        double timeHours = dtSeconds / 3600.0;
        double totalEnergyKwh = (power.totalWatts / 1000.0) * timeHours;
        double totalCarbonGrams = totalEnergyKwh * intensity.intensity;

        int currentHour = TimeUtil::CurrentHour();

        // Energy shares: CPU-proportional while tracked apps are busy, else 10 %
        // for the foreground app and 2 % in the background. The rest goes to
        // the "other" row.
        bool busy = totalTrackedCpu > 0.1 && systemCpuUsage > 0.1;
        std::vector<std::pair<std::string, double>> shares;
        double shareSum = 0.0;
        for (const auto& target : appsToTrack) {
            auto cpuIt = perAppCpu.find(target);
            double appCpuPercent = (cpuIt != perAppCpu.end()) ? cpuIt->second : 0.0;

            // Skip if app is not running
            if (appCpuPercent <= 0.0 && !ProcessMonitor::IsProcessRunning(target))
                continue;

            // A foreground browser on a non-matching tab gets nothing
            bool isForeground = AppKey(activeApp) == AppKey(target);
            if (isForeground && !MatchesBrowserTabFilter(target, windowTitle))
                continue;

            double share;
            if (busy) {
                share = appCpuPercent / std::max(systemCpuUsage, totalTrackedCpu);
            } else if (isForeground) {
                share = 0.10;
            } else {
                share = 0.02;
            }
            shares.push_back({target, share});
            shareSum += share;
        }
        double scale = shareSum > 1.0 ? 1.0 / shareSum : 1.0;

        {
            std::lock_guard<std::mutex> lock(dataMutex_);
            totalSessionSeconds_ += dtSeconds;
            totalSessionEnergyKwh_ += totalEnergyKwh;
            totalSessionCarbonGrams_ += totalCarbonGrams;

            // Track brightness
            brightnessHistory_.push_back({TimeUtil::SecondsSinceEpoch(), brightness});

            auto accumulate = [&](const std::string& name, double energyKwh, double cpu) {
                double carbonGrams = energyKwh * intensity.intensity;
                auto& app = appData_[name];
                app.appName = name;
                app.totalActiveSeconds += dtSeconds;
                app.totalEnergyKwh += energyKwh;
                app.totalCarbonGrams += carbonGrams;
                app.carbonByHour[currentHour] += carbonGrams;
                app.energyByHour[currentHour] += energyKwh;
                app.secondsByHour[currentHour] += dtSeconds;
                app.sampleCount++;
                app.avgCpuPercent = ((app.avgCpuPercent * (app.sampleCount - 1)) + cpu) / app.sampleCount;
                app.peakCpuPercent = std::max(app.peakCpuPercent, cpu);
            };

            for (const auto& [target, share] : shares) {
                auto cpuIt = perAppCpu.find(target);
                accumulate(target, totalEnergyKwh * share * scale,
                           cpuIt != perAppCpu.end() ? cpuIt->second : 0.0);
            }
            accumulate(OTHER_APP_NAME,
                       totalEnergyKwh * std::max(1.0 - shareSum * scale, 0.0),
                       std::max(systemCpuUsage - totalTrackedCpu, 0.0));
        }

        // Print live status every 10 ticks
        tickCount++;
        if (tickCount % 10 == 0) {
            std::string powerTag;
            if (power.systemMeasured) {
                powerTag = " (sys:battery)";
            } else {
                powerTag = " (cpu:" + power.cpuSource + ",gpu:" + power.gpuSource + ")";
            }
            std::cout << "\r[" << TimeUtil::Now() << "] "
                      << "Active: " << activeApp
                      << " | CPU: " << std::fixed << std::setprecision(1) << systemCpuUsage << "%"
                      << " | Power: " << std::setprecision(1) << power.totalWatts << "W" << powerTag
                      << " | CO2: " << std::setprecision(2) << totalSessionCarbonGrams_ << "g"
                      << " | Intensity: " << std::setprecision(0) << intensity.intensity << "g/kWh"
                      << "     " << std::flush;
        }

        // Stop() wakes this wait
        std::unique_lock<std::mutex> lock(stopMutex_);
        stopCv_.wait_for(lock, std::chrono::seconds(config_.updateIntervalSeconds),
                         [this] { return !running_; });
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
    running_ = false;
    {
        std::lock_guard<std::mutex> lock(stopMutex_);
    }
    stopCv_.notify_all();
    if (!monitorThread_.joinable() && !apiThread_.joinable()) return;
    std::cout << "\n\nStopping Carbon Footprint Tracker...\n";

    if (monitorThread_.joinable()) monitorThread_.join();
    if (apiThread_.joinable()) apiThread_.join();
}

void CarbonEngine::RequestStop() {
    running_ = false;  // async-signal-safe
}

double CarbonEngine::GetSessionStartEpoch() const {
    return sessionStartTime_;
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
    const std::string key = AppKey(appName);
    if (key.empty()) return;
    // A re-added app is active again
    for (auto& [name, data] : appData_) {
        if (AppKey(name) == key) data.isActive = true;
    }
    for (const auto& existing : config_.targetApps) {
        if (AppKey(existing) == key) return; // already exists
    }
    config_.targetApps.push_back(appName);
}

void CarbonEngine::RemoveApp(const std::string& appName) {
    std::lock_guard<std::mutex> lock(dataMutex_);
    const std::string key = AppKey(appName);

    config_.targetApps.erase(
        std::remove_if(config_.targetApps.begin(), config_.targetApps.end(),
            [&](const std::string& s) { return AppKey(s) == key; }),
        config_.targetApps.end());

    // Mark existing data as inactive but KEEP it for the report
    for (auto& [name, data] : appData_) {
        if (AppKey(name) == key) data.isActive = false;
    }
}

std::vector<std::string> CarbonEngine::GetActiveApps() {
    std::lock_guard<std::mutex> lock(dataMutex_);
    return config_.targetApps;
}

// --- Browser tab filter ---

bool CarbonEngine::MatchesBrowserTabFilter(const std::string& appName, const std::string& windowTitle) {
    // Check if this app has a tab filter configured
    const std::string key = AppKey(appName);

    for (const auto& filter : config_.tabFilters) {
        if (!filter.enabled) continue;
        if (AppKey(filter.browserProcess) == key) {
            // This app has a tab filter - check if current window title matches
            if (windowTitle.empty()) return false;
            return LowerCopy(windowTitle).find(LowerCopy(filter.titleFilter)) != std::string::npos;
        }
    }
    // No filter for this app - always track
    return true;
}

void CarbonEngine::AddTabFilter(const BrowserTabFilter& filter) {
    std::lock_guard<std::mutex> lock(dataMutex_);
    // Replace existing filter for same browser
    for (auto& f : config_.tabFilters) {
        if (AppKey(f.browserProcess) == AppKey(filter.browserProcess)) {
            f = filter;
            return;
        }
    }
    config_.tabFilters.push_back(filter);
}

void CarbonEngine::RemoveTabFilter(const std::string& browserProcess) {
    std::lock_guard<std::mutex> lock(dataMutex_);
    const std::string key = AppKey(browserProcess);
    config_.tabFilters.erase(
        std::remove_if(config_.tabFilters.begin(), config_.tabFilters.end(),
            [&](const BrowserTabFilter& f) { return AppKey(f.browserProcess) == key; }),
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
    if (!(futureHours > 0.0)) return proj;

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
        // Skip invalid imported values
        if (s.durationSeconds <= 0 || s.carbonGrams < 0 || s.energyKwh < 0) continue;
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
