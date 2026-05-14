#include "platform.h"
#include "process_monitor.h"
#include "power_monitor.h"
#include "screen_monitor.h"
#include "carbon_api.h"
#include "carbon_engine.h"
#include "report.h"
#include "daemon.h"
#include "hardware_detect.h"

// ============================================================
// Carbon Footprint Tracker - Main Entry Point
// ============================================================

static CarbonEngine* g_engine = nullptr;

static void PrintBanner() {
    std::cout << R"(
  ____            _                   _____           _             _       _
 / ___|__ _ _ __ | |__   ___  _ __   |  ___|__   ___ | |_ _ __  _ __(_)_ __ | |_
| |   / _` | '_ \| '_ \ / _ \| '_ \  | |_ / _ \ / _ \| __| '_ \| '__| | '_ \| __|
| |__| (_| | |  | | | | (_) | | | | |  _| (_) | (_) | |_| |_) | |  | | | | | |_
 \____\__,_|_|  |_|_| |_|\___/|_| |_| |_|  \___/ \___/ \__| .__/|_|  |_|_| |_|\__|
                                                            |_|
   ______             __
  /_  __/______ _____/ /_____ ____
   / / / __/ _ `/ __/  '_/ -_) __/
  /_/ /_/  \_,_/\__/_/\_\\__/_/     v1.1.2

)" << std::endl;
}

// ============================================================
// SETUP MENU (before monitoring starts)
// ============================================================

static void PrintSetupMenu() {
    std::cout << "\n=== SETUP MENU ===\n\n";
    std::cout << "  1. List running processes\n";
    std::cout << "  2. Add application to monitor\n";
    std::cout << "  3. Remove application from monitor\n";
    std::cout << "  4. Show monitored applications\n";
    std::cout << "  5. Set region/zone for carbon intensity\n";
    std::cout << "  6. Configure system parameters\n";
    std::cout << "  7. Import previous session data\n";
    std::cout << "  8. Show current carbon intensity\n";
    std::cout << "  9. START monitoring\n";
    std::cout << " 10. Browser tab filters (track specific tabs)\n";
    std::cout << " 11. Re-detect hardware\n";
    std::cout << " 12. Import session from JSON file\n";
    std::cout << "  0. Exit\n";
    std::cout << "\n> ";
}

static void ListProcesses() {
    std::cout << "\nScanning running processes...\n\n";
    auto processes = ProcessMonitor::ListRunningProcesses();

    int count = 0;
    for (const auto& p : processes) {
        if (p.name.empty() || p.name == "<unknown>") continue;
        std::cout << "  " << std::left << std::setw(35) << p.name
                  << "(PID: " << p.pid << ")\n";
        count++;
    }
    std::cout << "\nTotal: " << count << " unique processes found.\n";
}

static void AddApplication(std::vector<std::string>& apps) {
    std::cout << "\nEnter application name (e.g., Code.exe, chrome.exe, firefox):\n> ";
    std::string appName;
    std::getline(std::cin, appName);

    if (appName.empty()) {
        std::cout << "No application name entered.\n";
        return;
    }

    // Check for duplicates
    for (const auto& a : apps) {
        std::string l1 = a, l2 = appName;
        std::transform(l1.begin(), l1.end(), l1.begin(), ::tolower);
        std::transform(l2.begin(), l2.end(), l2.begin(), ::tolower);
        if (l1 == l2) {
            std::cout << "Application '" << appName << "' is already in the list.\n";
            return;
        }
    }

    apps.push_back(appName);
    std::cout << "Added '" << appName << "' to monitoring list.\n";
}

static void RemoveApplication(std::vector<std::string>& apps) {
    if (apps.empty()) {
        std::cout << "No applications in monitoring list.\n";
        return;
    }

    std::cout << "\nMonitored applications:\n";
    for (size_t i = 0; i < apps.size(); ++i) {
        std::cout << "  " << (i + 1) << ". " << apps[i] << "\n";
    }
    std::cout << "\nEnter number to remove (0 to cancel):\n> ";

    std::string input;
    std::getline(std::cin, input);
    try {
        int idx = std::stoi(input);
        if (idx > 0 && idx <= static_cast<int>(apps.size())) {
            std::cout << "Removed '" << apps[idx - 1] << "'.\n";
            apps.erase(apps.begin() + idx - 1);
        } else if (idx != 0) {
            std::cout << "Invalid selection.\n";
        }
    } catch (...) {
        std::cout << "Invalid input.\n";
    }
}

static void ShowMonitored(const std::vector<std::string>& apps) {
    if (apps.empty()) {
        std::cout << "\nNo applications configured for monitoring.\n";
        std::cout << "Use option 2 to add applications.\n";
        return;
    }
    std::cout << "\nMonitored applications:\n";
    for (size_t i = 0; i < apps.size(); ++i) {
        std::cout << "  " << (i + 1) << ". " << apps[i] << "\n";
    }
}

static void SetZone(std::string& zone) {
    auto zones = CarbonAPI::GetCommonZones();

    std::cout << "\nAvailable regions/zones:\n\n";
    for (size_t i = 0; i < zones.size(); ++i) {
        std::cout << "  " << std::setw(3) << (i + 1) << ". "
                  << std::left << std::setw(10) << zones[i].first
                  << zones[i].second << "\n";
    }
    std::cout << "\nEnter zone code (e.g., PL) or number from list:\n";
    std::cout << "Current zone: " << zone << "\n> ";

    std::string input;
    std::getline(std::cin, input);

    if (input.empty()) return;

    // Try as number first
    try {
        int idx = std::stoi(input);
        if (idx > 0 && idx <= static_cast<int>(zones.size())) {
            zone = zones[idx - 1].first;
            std::cout << "Zone set to: " << zone << " (" << zones[idx - 1].second << ")\n";
            return;
        }
    } catch (...) {}

    // Treat as zone code
    zone = input;
    std::cout << "Zone set to: " << zone << "\n";
}

static void ConfigureSystem(EngineConfig& config) {
    std::cout << "\n=== System Configuration ===\n\n";
    std::cout << "Current settings:\n";
    std::cout << "  1. CPU TDP:            " << config.cpuTdpWatts << " W\n";
    std::cout << "  2. GPU TDP:            " << config.gpuTdpWatts << " W\n";
    std::cout << "  3. Base System Power:  " << config.baseSystemWatts << " W\n";
    std::cout << "  4. System Type:        " << (config.isLaptop ? "Laptop" : "Desktop") << "\n";
    std::cout << "  5. Update Interval:    " << config.updateIntervalSeconds << " s\n";
    std::cout << "  6. API Key:            " << (config.apiKey.empty() ? "(not set)" : "****") << "\n";
    std::cout << "  0. Back to main menu\n";
    std::cout << "\nSelect setting to change:\n> ";

    std::string input;
    std::getline(std::cin, input);

    try {
        int choice = std::stoi(input);
        switch (choice) {
            case 1: {
                std::cout << "Enter CPU TDP in Watts (typical: 15-125):\n> ";
                std::getline(std::cin, input);
                config.cpuTdpWatts = std::stod(input);
                break;
            }
            case 2: {
                std::cout << "Enter GPU TDP in Watts (typical: 75-350, 0 for integrated):\n> ";
                std::getline(std::cin, input);
                config.gpuTdpWatts = std::stod(input);
                break;
            }
            case 3: {
                std::cout << "Enter base system power in Watts (typical: 20-50):\n> ";
                std::getline(std::cin, input);
                config.baseSystemWatts = std::stod(input);
                break;
            }
            case 4: {
                config.isLaptop = !config.isLaptop;
                std::cout << "System type changed to: " << (config.isLaptop ? "Laptop" : "Desktop") << "\n";
                break;
            }
            case 5: {
                std::cout << "Enter update interval in seconds (1-60):\n> ";
                std::getline(std::cin, input);
                int val = std::stoi(input);
                if (val >= 1 && val <= 60) config.updateIntervalSeconds = val;
                else std::cout << "Invalid interval. Must be 1-60.\n";
                break;
            }
            case 6: {
                std::cout << "Enter Electricity Maps API key (or empty to clear):\n> ";
                std::getline(std::cin, config.apiKey);
                break;
            }
            default: break;
        }
    } catch (...) {
        std::cout << "Invalid input.\n";
    }
}

static void ShowIntensity(const std::string& zone, const std::string& apiKey) {
    CarbonAPI api(zone, apiKey);
    std::cout << "\nFetching carbon intensity for zone: " << zone << "...\n";
    bool success = api.FetchLatest();
    auto data = api.GetIntensity();

    std::cout << "  Carbon Intensity: " << std::fixed << std::setprecision(1)
              << data.intensity << " gCO2eq/kWh\n";
    std::cout << "  Data Source:      " << (data.isRealData ? "Electricity Maps API (live)" : "Fallback estimate") << "\n";
    std::cout << "  Time:             " << data.datetime << "\n";

    if (!success) {
        std::cout << "\n  Note: Could not reach Electricity Maps API.\n";
        std::cout << "  Set an API key (option 6 in config) for live data.\n";
        std::cout << "  Get a free key at: https://api-portal.electricitymaps.com/\n";
    }
}

// ============================================================
// IMPORT PREVIOUS SESSION
// ============================================================

static void ImportPreviousSession(std::vector<PreviousSession>& sessions) {
    PreviousSession s;

    std::cout << "\n=== Import Previous Session ===\n\n";
    std::cout << "Enter a short description (e.g., 'Python coding Monday'):\n> ";
    std::getline(std::cin, s.description);
    if (s.description.empty()) s.description = "Session " + std::to_string(sessions.size() + 1);

    std::string input;

    std::cout << "Duration in hours (e.g., 3.5):\n> ";
    std::getline(std::cin, input);
    try { s.durationSeconds = std::stod(input) * 3600.0; }
    catch (...) { std::cout << "Invalid. Cancelled.\n"; return; }

    std::cout << "Total CO2 in grams (e.g., 15.5):\n> ";
    std::getline(std::cin, input);
    try { s.carbonGrams = std::stod(input); }
    catch (...) { std::cout << "Invalid. Cancelled.\n"; return; }

    std::cout << "Total energy in Wh (e.g., 45.2)  [enter 0 to auto-estimate]:\n> ";
    std::getline(std::cin, input);
    try { s.energyKwh = std::stod(input) / 1000.0; }
    catch (...) { s.energyKwh = 0; }
    if (s.energyKwh <= 0.0 && s.carbonGrams > 0) {
        s.avgIntensity = 400.0;
        s.energyKwh = s.carbonGrams / s.avgIntensity;
    }

    std::cout << "Average grid intensity gCO2/kWh (press Enter for auto):\n> ";
    std::getline(std::cin, input);
    if (!input.empty()) {
        try { s.avgIntensity = std::stod(input); } catch (...) {}
    }
    if (s.avgIntensity <= 0 && s.energyKwh > 0) {
        s.avgIntensity = s.carbonGrams / s.energyKwh;
    }

    // Optional per-app breakdown
    std::cout << "Add per-app CO2 breakdown? (y/n):\n> ";
    std::getline(std::cin, input);
    if (!input.empty() && (input[0] == 'y' || input[0] == 'Y')) {
        while (true) {
            std::cout << "  App name (empty to finish):\n  > ";
            std::string appName;
            std::getline(std::cin, appName);
            if (appName.empty()) break;

            std::cout << "  CO2 grams for '" << appName << "':\n  > ";
            std::getline(std::cin, input);
            try {
                double co2 = std::stod(input);
                s.appCarbonGrams[appName] = co2;
            } catch (...) { std::cout << "  Invalid, skipping.\n"; }
        }
    }

    sessions.push_back(s);
    std::cout << "\nImported session: '" << s.description << "' ("
              << std::fixed << std::setprecision(1) << s.durationSeconds / 3600.0
              << "h, " << std::setprecision(2) << s.carbonGrams << "g CO2)\n";
}

// ============================================================
// BROWSER TAB FILTER MENU
// ============================================================

static void ManageTabFilters(std::vector<BrowserTabFilter>& filters) {
    std::cout << "\n=== BROWSER TAB FILTERS ===\n\n";
    std::cout << "  Track only specific browser tabs for project-based tracking.\n";
    std::cout << "  Example: Track Firefox only when 'GitHub' or 'Jira' is in the tab title.\n\n";

    if (!filters.empty()) {
        std::cout << "  Current filters:\n";
        for (size_t i = 0; i < filters.size(); ++i) {
            std::cout << "    " << (i + 1) << ". " << filters[i].browserProcess
                      << " -> title contains: \"" << filters[i].titleFilter << "\""
                      << (filters[i].enabled ? " [active]" : " [disabled]") << "\n";
        }
        std::cout << "\n";
    } else {
        std::cout << "  No tab filters configured (all browser activity is tracked).\n\n";
    }

    std::cout << "  1. Add new tab filter\n";
    std::cout << "  2. Remove tab filter\n";
    std::cout << "  3. Toggle filter on/off\n";
    std::cout << "  0. Back to main menu\n";
    std::cout << "\n> ";

    std::string input;
    std::getline(std::cin, input);
    if (input.empty()) return;

    try {
        int choice = std::stoi(input);
        switch (choice) {
            case 1: {
                std::cout << "\nBrowser process name (e.g., firefox.exe, chrome.exe, msedge.exe):\n> ";
                std::string browser;
                std::getline(std::cin, browser);
                if (browser.empty()) { std::cout << "Cancelled.\n"; return; }

                std::cout << "Title keyword to match (e.g., 'GitHub', 'project-name', 'Stack Overflow'):\n> ";
                std::string keyword;
                std::getline(std::cin, keyword);
                if (keyword.empty()) { std::cout << "Cancelled.\n"; return; }

                filters.push_back(BrowserTabFilter(browser, keyword));
                std::cout << "Added filter: " << browser << " -> \"" << keyword << "\"\n";
                std::cout << "Only " << browser << " tabs with '" << keyword << "' in the title will be tracked.\n";
                break;
            }
            case 2: {
                if (filters.empty()) { std::cout << "No filters to remove.\n"; return; }
                std::cout << "Enter number to remove (0 to cancel):\n> ";
                std::getline(std::cin, input);
                int idx = std::stoi(input);
                if (idx > 0 && idx <= static_cast<int>(filters.size())) {
                    std::cout << "Removed filter for " << filters[idx-1].browserProcess << ".\n";
                    filters.erase(filters.begin() + idx - 1);
                }
                break;
            }
            case 3: {
                if (filters.empty()) { std::cout << "No filters to toggle.\n"; return; }
                std::cout << "Enter number to toggle (0 to cancel):\n> ";
                std::getline(std::cin, input);
                int idx = std::stoi(input);
                if (idx > 0 && idx <= static_cast<int>(filters.size())) {
                    filters[idx-1].enabled = !filters[idx-1].enabled;
                    std::cout << "Filter for " << filters[idx-1].browserProcess << " is now "
                              << (filters[idx-1].enabled ? "ACTIVE" : "DISABLED") << ".\n";
                }
                break;
            }
            default: break;
        }
    } catch (...) {
        std::cout << "Invalid input.\n";
    }
}

// ============================================================
// LIVE MONITORING MENU (while tracker is running)
// ============================================================

static void PrintLiveMenu() {
    std::cout << "\n--- MONITORING ACTIVE ---\n";
    std::cout << "  Commands:\n";
    std::cout << "    add <app>       - Add application to monitor\n";
    std::cout << "    remove <app>    - Remove app (data kept for report)\n";
    std::cout << "    list            - Show monitored apps\n";
    std::cout << "    status          - Show current tracking status\n";
    std::cout << "    detail          - Show per-app CPU & energy breakdown\n";
    std::cout << "    filter <browser> <keyword> - Add browser tab filter\n";
    std::cout << "    project <hours> - Project future CO2 for given hours\n";
    std::cout << "    import          - Import a previous session\n";
    std::cout << "    stop / quit     - Stop monitoring & generate report\n";
    std::cout << "  > ";
}

static void LiveInteractionLoop(CarbonEngine& engine) {
    std::string line;

    PrintLiveMenu();

    while (engine.IsRunning()) {
        if (!std::getline(std::cin, line)) {
            // EOF or Ctrl+C
            break;
        }

        if (line.empty()) {
            if (engine.IsRunning()) std::cout << "  > ";
            continue;
        }

        // Parse command
        std::string cmd, arg;
        {
            std::istringstream iss(line);
            iss >> cmd;
            std::getline(iss >> std::ws, arg);
        }
        std::transform(cmd.begin(), cmd.end(), cmd.begin(), ::tolower);

        if (cmd == "stop" || cmd == "quit" || cmd == "exit" || cmd == "q") {
            engine.Stop();
            break;
        }
        else if (cmd == "add") {
            if (arg.empty()) {
                std::cout << "  Enter app name to add:\n  > ";
                std::getline(std::cin, arg);
            }
            if (!arg.empty()) {
                engine.AddApp(arg);
                std::cout << "  Added '" << arg << "' to monitoring.\n";
            }
        }
        else if (cmd == "remove" || cmd == "rm" || cmd == "del") {
            if (arg.empty()) {
                auto apps = engine.GetActiveApps();
                if (apps.empty()) {
                    std::cout << "  No apps being monitored.\n";
                } else {
                    std::cout << "  Currently monitoring:\n";
                    for (size_t i = 0; i < apps.size(); ++i) {
                        std::cout << "    " << (i + 1) << ". " << apps[i] << "\n";
                    }
                    std::cout << "  Enter app name or number (0 to cancel):\n  > ";
                    std::getline(std::cin, arg);
                    if (arg.empty()) { std::cout << "  > "; continue; }

                    try {
                        int idx = std::stoi(arg);
                        if (idx > 0 && idx <= static_cast<int>(apps.size())) {
                            arg = apps[idx - 1];
                        } else if (idx == 0) { std::cout << "  > "; continue; }
                    } catch (...) {} // treat as name
                }
            }
            if (!arg.empty()) {
                engine.RemoveApp(arg);
                std::cout << "  Removed '" << arg << "' from monitoring (data preserved).\n";
            }
        }
        else if (cmd == "list" || cmd == "apps" || cmd == "ls") {
            auto apps = engine.GetActiveApps();
            auto allData = engine.GetAppData();

            std::cout << "\n  Active monitored apps:\n";
            if (apps.empty()) {
                std::cout << "    (none)\n";
            } else {
                for (size_t i = 0; i < apps.size(); ++i) {
                    std::cout << "    " << (i + 1) << ". " << apps[i] << "\n";
                }
            }

            bool hasRemoved = false;
            for (const auto& [name, data] : allData) {
                if (!data.isActive) {
                    if (!hasRemoved) {
                        std::cout << "\n  Removed apps (data preserved):\n";
                        hasRemoved = true;
                    }
                    std::cout << "    - " << name << " ("
                              << std::fixed << std::setprecision(2)
                              << data.totalCarbonGrams << "g CO2 tracked)\n";
                }
            }
            std::cout << "\n";
        }
        else if (cmd == "status" || cmd == "stat" || cmd == "s") {
            ReportGenerator::PrintLiveStatus(engine);
            std::cout << "\n";

            auto appData = engine.GetAppData();
            if (!appData.empty()) {
                std::cout << "  Per-app:\n";
                for (const auto& [name, data] : appData) {
                    std::cout << "    " << std::left << std::setw(20) << name
                              << std::right
                              << " time=" << TimeUtil::FormatDuration(data.totalActiveSeconds)
                              << " CO2=" << std::fixed << std::setprecision(2)
                              << data.totalCarbonGrams << "g"
                              << " CPU=" << std::setprecision(1) << data.avgCpuPercent << "%"
                              << (data.isActive ? "" : " [removed]")
                              << "\n";
                }
            }
        }
        else if (cmd == "detail" || cmd == "details" || cmd == "d") {
            auto appData = engine.GetAppData();
            if (appData.empty()) {
                std::cout << "  No app data yet.\n";
            } else {
                std::cout << "\n  === PER-APPLICATION ENERGY BREAKDOWN ===\n\n";
                std::cout << "  " << std::left << std::setw(20) << "Application"
                          << std::right << std::setw(10) << "CPU avg"
                          << std::setw(10) << "CPU peak"
                          << std::setw(12) << "Energy(Wh)"
                          << std::setw(12) << "CO2(g)"
                          << std::setw(10) << "Time"
                          << "\n";
                std::cout << "  " << std::string(74, '-') << "\n";
                for (const auto& [name, data] : appData) {
                    std::cout << "  " << std::left << std::setw(20) << name
                              << std::right
                              << std::setw(9) << std::fixed << std::setprecision(1) << data.avgCpuPercent << "%"
                              << std::setw(9) << std::setprecision(1) << data.peakCpuPercent << "%"
                              << std::setw(12) << std::setprecision(4) << data.totalEnergyKwh * 1000.0
                              << std::setw(12) << std::setprecision(4) << data.totalCarbonGrams
                              << std::setw(10) << TimeUtil::FormatDuration(data.totalActiveSeconds)
                              << (data.isActive ? "" : " [removed]")
                              << "\n";
                }
                std::cout << "\n";
            }
        }
        else if (cmd == "filter") {
            // filter <browser> <keyword>
            if (arg.empty()) {
                // Show current filters
                auto filters = engine.GetTabFilters();
                if (filters.empty()) {
                    std::cout << "  No tab filters. Usage: filter <browser> <keyword>\n";
                    std::cout << "  Example: filter firefox.exe GitHub\n";
                } else {
                    std::cout << "  Active tab filters:\n";
                    for (const auto& f : filters) {
                        std::cout << "    " << f.browserProcess << " -> \"" << f.titleFilter << "\"\n";
                    }
                }
            } else {
                std::istringstream argStream(arg);
                std::string browser, keyword;
                argStream >> browser;
                std::getline(argStream >> std::ws, keyword);
                if (!browser.empty() && !keyword.empty()) {
                    engine.AddTabFilter(BrowserTabFilter(browser, keyword));
                    std::cout << "  Added tab filter: " << browser << " -> \"" << keyword << "\"\n";
                } else {
                    std::cout << "  Usage: filter <browser> <keyword>\n";
                    std::cout << "  Example: filter firefox.exe GitHub\n";
                }
            }
        }
        else if (cmd == "project" || cmd == "proj" || cmd == "forecast") {
            double hours = 0;
            if (!arg.empty()) {
                try { hours = std::stod(arg); } catch (...) {}
            }
            if (hours <= 0) {
                std::cout << "  How many future hours to project? (e.g., 4):\n  > ";
                std::getline(std::cin, arg);
                try { hours = std::stod(arg); } catch (...) { hours = 0; }
            }
            if (hours > 0) {
                ReportGenerator::PrintProjection(engine, hours);
            } else {
                std::cout << "  Invalid hours.\n";
            }
        }
        else if (cmd == "import") {
            PreviousSession s;
            std::string inp;

            std::cout << "  Description (e.g., 'Python coding Monday'):\n  > ";
            std::getline(std::cin, s.description);
            if (s.description.empty()) s.description = "Imported session";

            std::cout << "  Duration in hours:\n  > ";
            std::getline(std::cin, inp);
            try { s.durationSeconds = std::stod(inp) * 3600.0; }
            catch (...) { std::cout << "  Invalid. Cancelled.\n"; std::cout << "  > "; continue; }

            std::cout << "  Total CO2 in grams:\n  > ";
            std::getline(std::cin, inp);
            try { s.carbonGrams = std::stod(inp); }
            catch (...) { std::cout << "  Invalid. Cancelled.\n"; std::cout << "  > "; continue; }

            std::cout << "  Total energy in Wh (0 to auto-estimate):\n  > ";
            std::getline(std::cin, inp);
            try { s.energyKwh = std::stod(inp) / 1000.0; } catch (...) { s.energyKwh = 0; }
            if (s.energyKwh <= 0 && s.carbonGrams > 0) {
                s.avgIntensity = 400.0;
                s.energyKwh = s.carbonGrams / s.avgIntensity;
            }

            engine.AddPreviousSession(s);
            std::cout << "  Imported '" << s.description << "'.\n";
        }
        else if (cmd == "help" || cmd == "h" || cmd == "?") {
            PrintLiveMenu();
            continue;
        }
        else {
            std::cout << "  Unknown command: '" << cmd << "'. Type 'help' for commands.\n";
        }

        if (engine.IsRunning()) {
            std::cout << "  > ";
        }
    }
}

// ============================================================
// START MONITORING
// ============================================================

static void StartMonitoring(EngineConfig& config, std::vector<PreviousSession>& prevSessions, bool asDaemon) {
    if (config.targetApps.empty()) {
        std::cout << "\nNo applications configured for monitoring!\n";
        std::cout << "Use option 2 to add applications first.\n";
        return;
    }

    if (asDaemon) {
#ifndef PLATFORM_WINDOWS
        std::cout << "\nStarting as background daemon...\n";
        if (!Daemon::Daemonize()) {
            std::cerr << "Failed to daemonize. Running in foreground instead.\n";
        }
#else
        std::cout << "\nOn Windows, running in foreground mode.\n";
#endif
    }

    g_engine = new CarbonEngine(config);

    // Import any previous sessions
    for (const auto& s : prevSessions) {
        g_engine->AddPreviousSession(s);
    }

    Daemon::InstallSignalHandlers([]() {
        if (g_engine) {
            g_engine->Stop();
        }
    });

    g_engine->Start();

    // Run interactive command loop on the main thread
    LiveInteractionLoop(*g_engine);

    if (g_engine->IsRunning()) {
        g_engine->Stop();
    }

    // Generate and print report
    std::cout << "\n";
    ReportGenerator::PrintReport(*g_engine);
    ReportGenerator::SaveReport(*g_engine);
    ReportGenerator::SaveReportJson(*g_engine);

    delete g_engine;
    g_engine = nullptr;
}

int main(int argc, char* argv[]) {
    EngineConfig config;
    config.zone = "PL";
    config.apiKey = "";
    config.updateIntervalSeconds = 2;
    config.cpuTdpWatts = 65.0;
    config.gpuTdpWatts = 150.0;
    config.baseSystemWatts = 30.0;
    config.isLaptop = true;
    config.autoDetectedHardware = false;

    // Start with no apps — user picks them
    config.targetApps = {};

    // Previous sessions storage
    std::vector<PreviousSession> previousSessions;

    // === AUTO-DETECT HARDWARE ===
    std::cout << "Detecting hardware...\n";
    HardwareInfo hwInfo = HardwareDetect::DetectAll();
    config.cpuTdpWatts = hwInfo.cpuTdpWatts;
    config.gpuTdpWatts = hwInfo.gpuTdpWatts;
    config.baseSystemWatts = hwInfo.baseSystemWatts;
    config.isLaptop = hwInfo.isLaptop;
    config.autoDetectedHardware = hwInfo.cpuDetected || hwInfo.gpuDetected;

    // === AUTO-DETECT COUNTRY/ZONE ===
    std::cout << "Detecting location for carbon intensity...\n";
    std::string detectedZone = CarbonAPI::AutoDetectZone();
    if (!detectedZone.empty()) {
        config.zone = detectedZone;
    }

    // Command-line quick start
    if (argc > 1) {
        for (int i = 1; i < argc; ++i) {
            std::string arg = argv[i];
            if (arg == "--zone" && i + 1 < argc) {
                config.zone = argv[++i];
            } else if (arg == "--apikey" && i + 1 < argc) {
                config.apiKey = argv[++i];
            } else if (arg == "--cpu-tdp" && i + 1 < argc) {
                config.cpuTdpWatts = std::stod(argv[++i]);
            } else if (arg == "--gpu-tdp" && i + 1 < argc) {
                config.gpuTdpWatts = std::stod(argv[++i]);
            } else if (arg == "--interval" && i + 1 < argc) {
                config.updateIntervalSeconds = std::stoi(argv[++i]);
            } else if (arg == "--app" && i + 1 < argc) {
                config.targetApps.push_back(argv[++i]);
            } else if (arg == "--desktop") {
                config.isLaptop = false;
            } else if (arg == "--filter" && i + 2 < argc) {
                std::string browser = argv[++i];
                std::string keyword = argv[++i];
                config.tabFilters.push_back(BrowserTabFilter(browser, keyword));
            } else if (arg == "--daemon") {
                // handled below
            } else if (arg == "--start") {
                // handled below
            } else if (arg == "--help" || arg == "-h") {
                std::cout << "Carbon Footprint Tracker v1.0\n\n";
                std::cout << "Usage: carbon_tracker [options]\n\n";
                std::cout << "Options:\n";
                std::cout << "  --start         Start monitoring immediately\n";
                std::cout << "  --daemon        Run as background daemon (Linux/Mac)\n";
                std::cout << "  --zone XX       Set electricity grid zone (e.g., PL, DE, US-CAL)\n";
                std::cout << "  --apikey KEY    Set Electricity Maps API key\n";
                std::cout << "  --app NAME      Add application to monitor (can be repeated)\n";
                std::cout << "  --cpu-tdp W     Set CPU TDP in Watts (auto-detected by default)\n";
                std::cout << "  --gpu-tdp W     Set GPU TDP in Watts (auto-detected by default)\n";
                std::cout << "  --interval S    Set update interval in seconds (default: 2)\n";
                std::cout << "  --desktop       Set system type to desktop (auto-detected by default)\n";
                std::cout << "  --filter BROWSER KEYWORD  Add browser tab filter\n";
                std::cout << "  --help, -h      Show this help\n";
                std::cout << "\nHardware power and country/zone are auto-detected at startup.\n";
                std::cout << "During monitoring, type 'help' for live commands:\n";
                std::cout << "  add/remove apps, status, detail, filter, project, import, stop\n";
                return 0;
            }
        }

        bool startNow = false;
        bool daemon = false;
        for (int i = 1; i < argc; ++i) {
            if (std::string(argv[i]) == "--start") startNow = true;
            if (std::string(argv[i]) == "--daemon") daemon = true;
        }

        if (startNow) {
            PrintBanner();
            StartMonitoring(config, previousSessions, daemon);
            return 0;
        }
    }

    // Interactive setup mode
    PrintBanner();

    // Show auto-detected hardware info
    HardwareDetect::PrintDetectedHardware(hwInfo);
    std::cout << "  Zone: " << config.zone << " (auto-detected)\n";

    std::string input;
    bool running = true;

    while (running) {
        PrintSetupMenu();
        std::getline(std::cin, input);

        if (input.empty()) continue;

        try {
            int choice = std::stoi(input);
            switch (choice) {
                case 1: ListProcesses(); break;
                case 2: AddApplication(config.targetApps); break;
                case 3: RemoveApplication(config.targetApps); break;
                case 4: ShowMonitored(config.targetApps); break;
                case 5: SetZone(config.zone); break;
                case 6: ConfigureSystem(config); break;
                case 7: ImportPreviousSession(previousSessions); break;
                case 8: ShowIntensity(config.zone, config.apiKey); break;
                case 9: {
                    StartMonitoring(config, previousSessions, false);
                    break;
                }
                case 10: ManageTabFilters(config.tabFilters); break;
                case 11: {
                    std::cout << "\nRe-detecting hardware...\n";
                    hwInfo = HardwareDetect::DetectAll();
                    config.cpuTdpWatts = hwInfo.cpuTdpWatts;
                    config.gpuTdpWatts = hwInfo.gpuTdpWatts;
                    config.baseSystemWatts = hwInfo.baseSystemWatts;
                    config.isLaptop = hwInfo.isLaptop;
                    HardwareDetect::PrintDetectedHardware(hwInfo);
                    break;
                }
                case 12: {
                    std::cout << "\nEnter path to JSON file (.json or .carbon.json):\n> ";
                    std::string jsonPath;
                    std::getline(std::cin, jsonPath);
                    if (!jsonPath.empty()) {
                        auto imported = ReportGenerator::ImportSessionsFromJson(jsonPath);
                        for (const auto& s : imported) {
                            previousSessions.push_back(s);
                        }
                        if (imported.empty()) {
                            std::cout << "No sessions found in file.\n";
                        } else {
                            std::cout << "Total " << imported.size() << " session(s) added to import list.\n";
                        }
                    }
                    break;
                }
                case 0: running = false; break;
                default: std::cout << "Invalid option.\n"; break;
            }
        } catch (...) {
            std::cout << "Invalid input. Enter a number 0-12.\n";
        }
    }

    std::cout << "\nGoodbye!\n";
    return 0;
}
