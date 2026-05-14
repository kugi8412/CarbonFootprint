#include "report.h"

// ============================================================
// Report Generator Implementation
// ============================================================

void ReportGenerator::PrintLiveStatus(CarbonEngine& engine) {
    double carbon = engine.GetTotalCarbonGrams();
    double energy = engine.GetTotalEnergyKwh();
    double duration = engine.GetSessionDurationSeconds();
    double intensity = engine.GetCurrentIntensity();

    std::cout << "\r[LIVE] Duration: " << TimeUtil::FormatDuration(duration)
              << " | Energy: " << std::fixed << std::setprecision(4) << energy << " kWh"
              << " | CO2: " << std::setprecision(2) << carbon << " g"
              << " | Grid: " << std::setprecision(0) << intensity << " gCO2/kWh"
              << "     " << std::flush;
}

static std::string GenerateReportText(CarbonEngine& engine) {
    std::ostringstream oss;

    double totalCarbon = engine.GetTotalCarbonGrams();
    double totalEnergy = engine.GetTotalEnergyKwh();
    double duration = engine.GetSessionDurationSeconds();
    auto appData = engine.GetAppData();
    auto brightnessHist = engine.GetBrightnessHistory();
    const auto& config = engine.GetConfig();

    oss << "\n";
    oss << "################################################################\n";
    oss << "#                                                              #\n";
    oss << "#           CARBON FOOTPRINT TRACKING REPORT                   #\n";
    oss << "#                                                              #\n";
    oss << "################################################################\n\n";

    // --- Session Summary ---
    oss << "=== SESSION SUMMARY ===\n\n";
    oss << "  Start Time:       " << engine.GetSessionStartTime() << "\n";
    oss << "  End Time:         " << TimeUtil::Now() << "\n";
    oss << "  Duration:         " << TimeUtil::FormatDuration(duration) << "\n";
    oss << "  Region/Zone:      " << config.zone << "\n";
    oss << "  Grid Intensity:   " << std::fixed << std::setprecision(1) << engine.GetCurrentIntensity() << " gCO2eq/kWh\n";
    oss << "\n";

    // --- Carbon Footprint ---
    oss << "=== CARBON FOOTPRINT ===\n\n";
    oss << "  Total Energy Consumed:    " << std::setprecision(6) << totalEnergy << " kWh\n";
    oss << "                            " << std::setprecision(2) << totalEnergy * 1000.0 << " Wh\n";
    oss << "  Total CO2 Emissions:      " << std::setprecision(4) << totalCarbon << " g\n";
    oss << "                            " << std::setprecision(6) << totalCarbon / 1000.0 << " kg\n";
    oss << "\n";

    // Equivalences
    oss << "  Equivalences:\n";
    double kmDriving = totalCarbon / 120.0; // ~120g CO2 per km for average car
    double phoneCharges = totalEnergy / 0.01; // ~10Wh per phone charge
    double treeDays = totalCarbon / 60.0; // tree absorbs ~60g CO2 per day
    oss << "    - Driving a car:     " << std::setprecision(4) << kmDriving << " km\n";
    oss << "    - Phone charges:     " << std::setprecision(2) << phoneCharges << " charges\n";
    oss << "    - Tree absorption:   would take " << std::setprecision(3) << treeDays << " tree-days to offset\n";
    oss << "\n";

    // --- Per-Application Breakdown ---
    if (!appData.empty()) {
        oss << "=== APPLICATION BREAKDOWN ===\n\n";
        oss << "  " << std::left << std::setw(25) << "Application"
            << std::right << std::setw(12) << "Time"
            << std::setw(15) << "Energy (Wh)"
            << std::setw(15) << "CO2 (g)"
            << std::setw(10) << "Share"
            << std::setw(10) << "CPU avg"
            << std::setw(10) << "CPU peak"
            << std::setw(10) << "Status"
            << "\n";
        oss << "  " << std::string(107, '-') << "\n";

        for (const auto& [name, data] : appData) {
            double share = (totalCarbon > 0) ? (data.totalCarbonGrams / totalCarbon * 100.0) : 0.0;
            oss << "  " << std::left << std::setw(25) << name
                << std::right << std::setw(12) << TimeUtil::FormatDuration(data.totalActiveSeconds)
                << std::setw(15) << std::setprecision(4) << data.totalEnergyKwh * 1000.0
                << std::setw(15) << std::setprecision(4) << data.totalCarbonGrams
                << std::setw(9) << std::setprecision(1) << share << "%"
                << std::setw(9) << std::setprecision(1) << data.avgCpuPercent << "%"
                << std::setw(9) << std::setprecision(1) << data.peakCpuPercent << "%"
                << std::setw(10) << (data.isActive ? "active" : "removed")
                << "\n";
        }
        oss << "\n";
        oss << "  Note: Energy is allocated proportionally based on per-process CPU usage.\n";
        oss << "        'removed' apps were unmonitored during the session but\n";
        oss << "        their accumulated data is preserved in this report.\n\n";
    }

    // --- Hourly Breakdown ---
    oss << "=== HOURLY BREAKDOWN ===\n\n";
    oss << "  Emissions by hour of day (shows hours with activity):\n\n";
    oss << "  " << std::left << std::setw(8) << "Hour"
        << std::right << std::setw(15) << "CO2 (g)"
        << std::setw(15) << "Energy (Wh)"
        << std::setw(30) << "Visual"
        << "\n";
    oss << "  " << std::string(68, '-') << "\n";

    // Aggregate hourly data across all apps
    std::map<int, double> totalCarbonByHour;
    std::map<int, double> totalEnergyByHour;
    double maxHourlyCO2 = 0;

    for (const auto& [name, data] : appData) {
        for (const auto& [hour, co2] : data.carbonByHour) {
            totalCarbonByHour[hour] += co2;
            if (totalCarbonByHour[hour] > maxHourlyCO2)
                maxHourlyCO2 = totalCarbonByHour[hour];
        }
        for (const auto& [hour, energy] : data.energyByHour) {
            totalEnergyByHour[hour] += energy;
        }
    }

    for (const auto& [hour, co2] : totalCarbonByHour) {
        int barLen = (maxHourlyCO2 > 0) ? static_cast<int>(co2 / maxHourlyCO2 * 25.0) : 0;
        std::string bar(barLen, '#');

        oss << "  " << std::left << std::setw(8)
            << (std::to_string(hour) + ":00")
            << std::right << std::setw(15) << std::setprecision(4) << co2
            << std::setw(15) << std::setprecision(4) << totalEnergyByHour[hour] * 1000.0
            << "  " << bar
            << "\n";
    }
    oss << "\n";

    // --- Screen Brightness Impact ---
    oss << "=== SCREEN BRIGHTNESS ANALYSIS ===\n\n";
    if (!brightnessHist.empty()) {
        double sumBrightness = 0;
        double minBrightness = 1.0;
        double maxBrightness = 0.0;
        for (const auto& [t, b] : brightnessHist) {
            sumBrightness += b;
            minBrightness = std::min(minBrightness, b);
            maxBrightness = std::max(maxBrightness, b);
        }
        double avgBrightness = sumBrightness / brightnessHist.size();

        oss << "  Average Brightness:     " << std::setprecision(0) << avgBrightness * 100.0 << "%\n";
        oss << "  Min Brightness:         " << std::setprecision(0) << minBrightness * 100.0 << "%\n";
        oss << "  Max Brightness:         " << std::setprecision(0) << maxBrightness * 100.0 << "%\n";

        // Estimate savings if brightness was 50%
        double actualScreenEnergy = 0;
        double half50Energy = 0;
        for (const auto& [t, b] : brightnessHist) {
            double interval = config.updateIntervalSeconds / 3600.0;
            actualScreenEnergy += ScreenMonitor::EstimateScreenPower(b, config.isLaptop) * interval / 1000.0;
            half50Energy += ScreenMonitor::EstimateScreenPower(0.5, config.isLaptop) * interval / 1000.0;
        }
        double savedEnergy = actualScreenEnergy - half50Energy;
        double savedCO2 = savedEnergy * engine.GetCurrentIntensity();

        if (avgBrightness > 0.55) {
            oss << "\n  TIP: Reducing brightness to 50% would save approximately:\n";
            oss << "    - " << std::setprecision(4) << std::abs(savedEnergy * 1000.0) << " Wh of energy\n";
            oss << "    - " << std::setprecision(4) << std::abs(savedCO2) << " g CO2\n";
        } else {
            oss << "\n  Great! Your screen brightness is already efficient.\n";
        }
    } else {
        oss << "  Screen brightness data not available on this system.\n";
    }
    oss << "\n";

    // --- System Configuration ---
    oss << "=== SYSTEM CONFIGURATION ===\n\n";
    oss << "  CPU TDP:             " << config.cpuTdpWatts << " W"
        << (config.autoDetectedHardware ? " (auto-detected)" : " (manual)") << "\n";
    oss << "  GPU TDP:             " << config.gpuTdpWatts << " W"
        << (config.autoDetectedHardware ? " (auto-detected)" : " (manual)") << "\n";
    oss << "  Base System Power:   " << config.baseSystemWatts << " W\n";
    oss << "  System Type:         " << (config.isLaptop ? "Laptop" : "Desktop")
        << (config.autoDetectedHardware ? " (auto-detected)" : "") << "\n";
    oss << "  Update Interval:     " << config.updateIntervalSeconds << " seconds\n";
    oss << "  Monitored Apps:      " << config.targetApps.size() << "\n";
    if (!config.tabFilters.empty()) {
        oss << "  Tab Filters:         " << config.tabFilters.size() << "\n";
        for (const auto& f : config.tabFilters) {
            oss << "    - " << f.browserProcess << " -> \"" << f.titleFilter << "\""
                << (f.enabled ? "" : " [disabled]") << "\n";
        }
    }
    oss << "\n";

    // --- Recommendations ---
    oss << "=== RECOMMENDATIONS ===\n\n";

    CarbonIntensityData intensityData = {engine.GetCurrentIntensity(), config.zone, "", false};
    if (intensityData.intensity > 500) {
        oss << "  [!] Your grid has HIGH carbon intensity (" << std::setprecision(0)
            << intensityData.intensity << " gCO2/kWh).\n";
        oss << "      Consider scheduling heavy workloads at times with more renewables.\n";
        oss << "      Typical low-carbon hours: 10:00-16:00 (solar) or windy periods.\n\n";
    } else if (intensityData.intensity > 200) {
        oss << "  [i] Your grid has MODERATE carbon intensity (" << std::setprecision(0)
            << intensityData.intensity << " gCO2/kWh).\n";
        oss << "      Shifting compute to off-peak hours can help reduce emissions.\n\n";
    } else {
        oss << "  [+] Your grid has LOW carbon intensity (" << std::setprecision(0)
            << intensityData.intensity << " gCO2/kWh). Great!\n\n";
    }

    if (duration > 3600 * 8) {
        oss << "  [!] Long session detected (" << TimeUtil::FormatDuration(duration) << ").\n";
        oss << "      Consider taking breaks to reduce continuous power consumption.\n\n";
    }

    // --- Previous Sessions ---
    auto prevSessions = engine.GetPreviousSessions();
    if (!prevSessions.empty()) {
        oss << "=== PREVIOUS SESSIONS (imported) ===\n\n";
        oss << "  " << std::left << std::setw(6) << "#"
            << std::setw(30) << "Description"
            << std::right << std::setw(12) << "Duration"
            << std::setw(15) << "CO2 (g)"
            << std::setw(15) << "Energy (Wh)"
            << "\n";
        oss << "  " << std::string(78, '-') << "\n";

        double totalPrevCarbon = 0;
        double totalPrevEnergy = 0;
        double totalPrevTime = 0;
        int idx = 1;
        for (const auto& s : prevSessions) {
            oss << "  " << std::left << std::setw(6) << idx++
                << std::setw(30) << s.description
                << std::right << std::setw(12) << TimeUtil::FormatDuration(s.durationSeconds)
                << std::setw(15) << std::setprecision(4) << s.carbonGrams
                << std::setw(15) << std::setprecision(4) << s.energyKwh * 1000.0
                << "\n";
            totalPrevCarbon += s.carbonGrams;
            totalPrevEnergy += s.energyKwh;
            totalPrevTime += s.durationSeconds;
        }
        oss << "  " << std::string(78, '-') << "\n";
        oss << "  " << std::left << std::setw(36) << "  TOTAL (previous)"
            << std::right << std::setw(12) << TimeUtil::FormatDuration(totalPrevTime)
            << std::setw(15) << std::setprecision(4) << totalPrevCarbon
            << std::setw(15) << std::setprecision(4) << totalPrevEnergy * 1000.0
            << "\n";
        oss << "\n";

        double grandCarbon = totalCarbon + totalPrevCarbon;
        double grandEnergy = totalEnergy + totalPrevEnergy;
        oss << "  GRAND TOTAL (all sessions):\n";
        oss << "    CO2:    " << std::setprecision(4) << grandCarbon << " g ("
            << std::setprecision(6) << grandCarbon / 1000.0 << " kg)\n";
        oss << "    Energy: " << std::setprecision(4) << grandEnergy * 1000.0 << " Wh ("
            << std::setprecision(6) << grandEnergy << " kWh)\n\n";
    }

    // --- Future Projection ---
    if (duration > 60 || !prevSessions.empty()) {
        double projHours[] = {1.0, 4.0, 8.0, 24.0};
        oss << "=== FUTURE PROJECTION ===\n\n";
        oss << "  Based on " << (prevSessions.empty() ? "current session" : "current + historical")
            << " data:\n\n";

        oss << "  " << std::left << std::setw(18) << "Future Work Time"
            << std::right << std::setw(18) << "Projected CO2 (g)"
            << std::setw(18) << "Projected (Wh)"
            << std::setw(18) << "Rate (g/h)"
            << "\n";
        oss << "  " << std::string(72, '-') << "\n";

        for (double h : projHours) {
            auto proj = engine.ProjectFuture(h);
            std::string label;
            if (h < 1.0) label = std::to_string(static_cast<int>(h * 60)) + " min";
            else if (h == 1.0) label = "1 hour";
            else label = std::to_string(static_cast<int>(h)) + " hours";

            oss << "  " << std::left << std::setw(18) << label
                << std::right << std::setw(18) << std::setprecision(4) << proj.projectedCarbonGrams
                << std::setw(18) << std::setprecision(4) << proj.projectedEnergyKwh * 1000.0
                << std::setw(18) << std::setprecision(2) << proj.avgCarbonPerHour
                << "\n";
        }
        oss << "\n";
    }

    oss << "################################################################\n";
    oss << "#  Report generated by Carbon Footprint Tracker v1.1.2        #\n";
    oss << "#  " << TimeUtil::Now() << std::string(46 - TimeUtil::Now().size(), ' ') << "#\n";
    oss << "################################################################\n";

    return oss.str();
}

void ReportGenerator::PrintReport(CarbonEngine& engine) {
    std::string report = GenerateReportText(engine);
    std::cout << report << std::endl;
}

std::string ReportGenerator::SaveReport(CarbonEngine& engine, const std::string& filename) {
    std::string fname = filename;
    if (fname.empty()) {
        // Generate filename with timestamp
        auto now = std::chrono::system_clock::now();
        auto t = std::chrono::system_clock::to_time_t(now);
        std::tm tm_buf{};
#ifdef PLATFORM_WINDOWS
        localtime_s(&tm_buf, &t);
#else
        localtime_r(&t, &tm_buf);
#endif
        char buf[64];
        std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &tm_buf);
        fname = std::string("carbon_report_") + buf + ".txt";
    }

    std::string report = GenerateReportText(engine);

    std::ofstream file(fname);
    if (file.is_open()) {
        file << report;
        file.close();
        std::cout << "\nReport saved to: " << fname << "\n";
    } else {
        std::cerr << "Failed to save report to: " << fname << "\n";
    }

    return fname;
}

void ReportGenerator::PrintProjection(CarbonEngine& engine, double futureHours) {
    auto proj = engine.ProjectFuture(futureHours);

    std::cout << "\n=== FUTURE CARBON FOOTPRINT PROJECTION ===\n\n";
    std::cout << "  Projection period:     " << std::fixed << std::setprecision(1)
              << futureHours << " hours\n";
    std::cout << "  Based on:              " << proj.totalDataSessions << " session(s)\n\n";

    if (proj.currentSessionRate > 0) {
        std::cout << "  Current session rate:  " << std::setprecision(4)
                  << proj.currentSessionRate << " gCO2/hour\n";
    }
    if (proj.historicalRate > 0) {
        std::cout << "  Historical rate:       " << std::setprecision(4)
                  << proj.historicalRate << " gCO2/hour\n";
    }
    std::cout << "  Combined avg rate:     " << std::setprecision(4)
              << proj.avgCarbonPerHour << " gCO2/hour\n\n";

    std::cout << "  --- Projected values ---\n";
    std::cout << "  CO2 emissions:         " << std::setprecision(4)
              << proj.projectedCarbonGrams << " g ("
              << std::setprecision(6) << proj.projectedCarbonGrams / 1000.0 << " kg)\n";
    std::cout << "  Energy consumed:       " << std::setprecision(4)
              << proj.projectedEnergyKwh * 1000.0 << " Wh ("
              << std::setprecision(6) << proj.projectedEnergyKwh << " kWh)\n";

    // Equivalences
    double kmDriving = proj.projectedCarbonGrams / 120.0;
    double phoneCharges = proj.projectedEnergyKwh / 0.01;
    std::cout << "\n  Equivalences:\n";
    std::cout << "    ~" << std::setprecision(4) << kmDriving << " km driving\n";
    std::cout << "    ~" << std::setprecision(2) << phoneCharges << " phone charges\n";
    std::cout << std::endl;
}

// ============================================================
// JSON Export - Compatible with Python GUI SessionData format
// ============================================================

static std::string EscapeJsonString(const std::string& s) {
    std::string result;
    result.reserve(s.size() + 10);
    for (char c : s) {
        switch (c) {
            case '"':  result += "\\\""; break;
            case '\\': result += "\\\\"; break;
            case '\n': result += "\\n";  break;
            case '\r': result += "\\r";  break;
            case '\t': result += "\\t";  break;
            default:   result += c;      break;
        }
    }
    return result;
}

std::string ReportGenerator::SaveReportJson(CarbonEngine& engine, const std::string& filename) {
    std::string fname = filename;
    if (fname.empty()) {
        auto now = std::chrono::system_clock::now();
        auto t = std::chrono::system_clock::to_time_t(now);
        std::tm tm_buf{};
#ifdef PLATFORM_WINDOWS
        localtime_s(&tm_buf, &t);
#else
        localtime_r(&t, &tm_buf);
#endif
        char buf[64];
        std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &tm_buf);
        fname = std::string("carbon_report_") + buf + ".json";
    }

    double totalCarbon = engine.GetTotalCarbonGrams();
    double totalEnergy = engine.GetTotalEnergyKwh();
    double duration = engine.GetSessionDurationSeconds();
    auto appData = engine.GetAppData();
    const auto& config = engine.GetConfig();
    double intensity = engine.GetCurrentIntensity();

    // Compute session start/end timestamps as Unix epoch seconds
    auto now = std::chrono::system_clock::now();
    double endTime = std::chrono::duration<double>(now.time_since_epoch()).count();
    double startTime = endTime - duration;

    std::ostringstream j;
    j << std::setprecision(15);

    j << "{\n";
    j << "  \"session_id\": \"session_" << static_cast<long long>(startTime) << "\",\n";
    j << "  \"description\": \"C++ tracking session\",\n";
    j << "  \"start_time\": " << startTime << ",\n";
    j << "  \"end_time\": " << endTime << ",\n";
    j << "  \"duration_seconds\": " << duration << ",\n";
    j << "  \"total_energy_kwh\": " << totalEnergy << ",\n";
    j << "  \"total_carbon_grams\": " << totalCarbon << ",\n";
    j << "  \"zone\": \"" << EscapeJsonString(config.zone) << "\",\n";
    j << "  \"avg_intensity\": " << intensity << ",\n";

    // Hardware
    j << "  \"hardware\": {\n";
    j << "    \"cpu_name\": \"" << EscapeJsonString("") << "\",\n";
    j << "    \"cpu_tdp_watts\": " << config.cpuTdpWatts << ",\n";
    j << "    \"cpu_cores\": 0,\n";
    j << "    \"gpu_name\": \"" << EscapeJsonString("") << "\",\n";
    j << "    \"gpu_tdp_watts\": " << config.gpuTdpWatts << ",\n";
    j << "    \"is_laptop\": " << (config.isLaptop ? "true" : "false") << ",\n";
    j << "    \"base_system_watts\": " << config.baseSystemWatts << ",\n";
    j << "    \"auto_detected\": " << (config.autoDetectedHardware ? "true" : "false") << "\n";
    j << "  },\n";

    // Apps
    j << "  \"apps\": {";
    bool firstApp = true;
    for (const auto& [name, data] : appData) {
        if (data.totalActiveSeconds <= 0 && data.totalCarbonGrams <= 0) continue;
        if (!firstApp) j << ",";
        firstApp = false;
        j << "\n    \"" << EscapeJsonString(name) << "\": {\n";
        j << "      \"app_name\": \"" << EscapeJsonString(name) << "\",\n";
        j << "      \"total_active_seconds\": " << data.totalActiveSeconds << ",\n";
        j << "      \"total_energy_kwh\": " << data.totalEnergyKwh << ",\n";
        j << "      \"total_carbon_grams\": " << data.totalCarbonGrams << ",\n";
        j << "      \"avg_cpu_percent\": " << data.avgCpuPercent << ",\n";
        j << "      \"peak_cpu_percent\": " << data.peakCpuPercent << ",\n";

        // carbon_by_hour
        j << "      \"carbon_by_hour\": {";
        bool firstH = true;
        for (const auto& [hour, co2] : data.carbonByHour) {
            if (!firstH) j << ", ";
            firstH = false;
            j << "\"" << hour << "\": " << co2;
        }
        j << "},\n";

        // energy_by_hour
        j << "      \"energy_by_hour\": {";
        firstH = true;
        for (const auto& [hour, energy] : data.energyByHour) {
            if (!firstH) j << ", ";
            firstH = false;
            j << "\"" << hour << "\": " << energy;
        }
        j << "},\n";

        j << "      \"is_active\": " << (data.isActive ? "true" : "false") << ",\n";
        j << "      \"sample_count\": " << data.sampleCount << "\n";
        j << "    }";
    }
    if (!firstApp) j << "\n  ";
    j << "}\n";
    j << "}\n";

    std::ofstream file(fname);
    if (file.is_open()) {
        file << j.str();
        file.close();
        std::cout << "JSON report saved to: " << fname << "\n";
    } else {
        std::cerr << "Failed to save JSON report to: " << fname << "\n";
    }

    return fname;
}

// ============================================================
// JSON Import - Read Python .json reports or .carbon.json projects
// ============================================================

// Extract a JSON sub-object by key (returns content between { })
static std::string ExtractJsonObject(const std::string& json, const std::string& key) {
    std::string searchKey = "\"" + key + "\"";
    size_t pos = json.find(searchKey);
    if (pos == std::string::npos) return "";

    pos = json.find('{', pos + searchKey.size());
    if (pos == std::string::npos) return "";

    int depth = 0;
    size_t start = pos;
    for (size_t i = pos; i < json.size(); ++i) {
        if (json[i] == '{') depth++;
        else if (json[i] == '}') { depth--; if (depth == 0) return json.substr(start, i - start + 1); }
    }
    return "";
}

// Extract a JSON array by key (returns content between [ ])
static std::string ExtractJsonArray(const std::string& json, const std::string& key) {
    std::string searchKey = "\"" + key + "\"";
    size_t pos = json.find(searchKey);
    if (pos == std::string::npos) return "";

    pos = json.find('[', pos + searchKey.size());
    if (pos == std::string::npos) return "";

    int depth = 0;
    size_t start = pos;
    for (size_t i = pos; i < json.size(); ++i) {
        if (json[i] == '[') depth++;
        else if (json[i] == ']') { depth--; if (depth == 0) return json.substr(start + 1, i - start - 1); }
    }
    return "";
}

// Split top-level JSON array elements (objects separated by commas at depth 0)
static std::vector<std::string> SplitJsonArrayElements(const std::string& arrayContent) {
    std::vector<std::string> elements;
    int depth = 0;
    size_t start = 0;
    for (size_t i = 0; i < arrayContent.size(); ++i) {
        char c = arrayContent[i];
        if (c == '{' || c == '[') depth++;
        else if (c == '}' || c == ']') depth--;
        else if (c == ',' && depth == 0) {
            std::string elem = arrayContent.substr(start, i - start);
            // Trim
            size_t a = elem.find('{');
            if (a != std::string::npos) elements.push_back(elem.substr(a));
            start = i + 1;
        }
    }
    // Last element
    std::string last = arrayContent.substr(start);
    size_t a = last.find('{');
    if (a != std::string::npos) elements.push_back(last.substr(a));
    return elements;
}

// Extract a simple JSON value by key from a JSON string
static std::string ExtractJsonField(const std::string& json, const std::string& key) {
    std::string searchKey = "\"" + key + "\"";
    size_t pos = json.find(searchKey);
    if (pos == std::string::npos) return "";

    pos = json.find(':', pos + searchKey.size());
    if (pos == std::string::npos) return "";
    pos++;

    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\n' || json[pos] == '\r')) pos++;
    if (pos >= json.size()) return "";

    if (json[pos] == '"') {
        size_t end = json.find('"', pos + 1);
        if (end == std::string::npos) return "";
        return json.substr(pos + 1, end - pos - 1);
    } else {
        size_t end = json.find_first_of(",}] \t\n\r", pos);
        if (end == std::string::npos) end = json.size();
        return json.substr(pos, end - pos);
    }
}

static PreviousSession ParseSessionJson(const std::string& json) {
    PreviousSession s;
    s.description = ExtractJsonField(json, "description");
    if (s.description.empty()) {
        s.description = ExtractJsonField(json, "session_id");
    }

    std::string durStr = ExtractJsonField(json, "duration_seconds");
    if (!durStr.empty()) { try { s.durationSeconds = std::stod(durStr); } catch (...) {} }

    std::string energyStr = ExtractJsonField(json, "total_energy_kwh");
    if (!energyStr.empty()) { try { s.energyKwh = std::stod(energyStr); } catch (...) {} }

    std::string carbonStr = ExtractJsonField(json, "total_carbon_grams");
    if (!carbonStr.empty()) { try { s.carbonGrams = std::stod(carbonStr); } catch (...) {} }

    std::string intensityStr = ExtractJsonField(json, "avg_intensity");
    if (!intensityStr.empty()) { try { s.avgIntensity = std::stod(intensityStr); } catch (...) {} }
    if (s.avgIntensity <= 0 && s.energyKwh > 0) {
        s.avgIntensity = s.carbonGrams / s.energyKwh;
    }

    // Parse per-app CO2 from "apps" object
    std::string appsObj = ExtractJsonObject(json, "apps");
    if (!appsObj.empty() && appsObj.size() > 2) {
        // Find each "app_name" => { ... "total_carbon_grams": X }
        size_t pos = 0;
        while (pos < appsObj.size()) {
            size_t nameStart = appsObj.find('"', pos);
            if (nameStart == std::string::npos) break;
            size_t nameEnd = appsObj.find('"', nameStart + 1);
            if (nameEnd == std::string::npos) break;
            std::string appName = appsObj.substr(nameStart + 1, nameEnd - nameStart - 1);

            // Skip keys like "app_name", "total_active_seconds" etc. inside nested objects
            size_t objStart = appsObj.find('{', nameEnd);
            if (objStart == std::string::npos) break;

            int depth = 0;
            size_t objEnd = objStart;
            for (size_t i = objStart; i < appsObj.size(); ++i) {
                if (appsObj[i] == '{') depth++;
                else if (appsObj[i] == '}') { depth--; if (depth == 0) { objEnd = i; break; } }
            }

            std::string appJson = appsObj.substr(objStart, objEnd - objStart + 1);
            std::string appCo2Str = ExtractJsonField(appJson, "total_carbon_grams");
            if (!appCo2Str.empty()) {
                try { s.appCarbonGrams[appName] = std::stod(appCo2Str); } catch (...) {}
            }

            pos = objEnd + 1;
        }
    }

    return s;
}

std::vector<PreviousSession> ReportGenerator::ImportSessionsFromJson(const std::string& filepath) {
    std::vector<PreviousSession> sessions;

    std::ifstream file(filepath);
    if (!file.is_open()) {
        std::cerr << "Failed to open file: " << filepath << "\n";
        return sessions;
    }

    std::string json((std::istreambuf_iterator<char>(file)),
                      std::istreambuf_iterator<char>());
    file.close();

    if (json.empty()) {
        std::cerr << "Empty file: " << filepath << "\n";
        return sessions;
    }

    // Check if this is a project file with a "sessions" array
    std::string sessionsArray = ExtractJsonArray(json, "sessions");
    if (!sessionsArray.empty()) {
        // Project file (.carbon.json) with multiple sessions
        auto elements = SplitJsonArrayElements(sessionsArray);
        for (const auto& elem : elements) {
            PreviousSession s = ParseSessionJson(elem);
            if (s.durationSeconds > 0 || s.carbonGrams > 0) {
                sessions.push_back(s);
            }
        }
        std::string projName = ExtractJsonField(json, "name");
        std::cout << "Imported " << sessions.size() << " session(s) from project"
                  << (projName.empty() ? "" : " '" + projName + "'") << ".\n";
    } else if (json.find("\"session_id\"") != std::string::npos) {
        // Single session report (.json)
        PreviousSession s = ParseSessionJson(json);
        if (s.durationSeconds > 0 || s.carbonGrams > 0) {
            sessions.push_back(s);
            std::cout << "Imported session: '" << s.description << "' ("
                      << std::fixed << std::setprecision(1) << s.durationSeconds / 3600.0
                      << "h, " << std::setprecision(2) << s.carbonGrams << "g CO2)\n";
        }
    } else {
        std::cerr << "Unrecognized JSON format in: " << filepath << "\n";
    }

    return sessions;
}
