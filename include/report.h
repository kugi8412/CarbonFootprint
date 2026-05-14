#pragma once
#include "platform.h"
#include "carbon_engine.h"

// ============================================================
// Report Generator - Produces detailed carbon footprint reports
// ============================================================

class ReportGenerator {
public:
    // Generate full text report and print to stdout
    static void PrintReport(CarbonEngine& engine);

    // Save detailed report to file, returns filename
    static std::string SaveReport(CarbonEngine& engine, const std::string& filename = "");

    // Save session data as JSON (compatible with Python GUI import), returns filename
    static std::string SaveReportJson(CarbonEngine& engine, const std::string& filename = "");

    // Import sessions from a JSON file (Python .json report or .carbon.json project)
    // Returns list of PreviousSession objects parsed from the file
    static std::vector<PreviousSession> ImportSessionsFromJson(const std::string& filepath);

    // Print a brief live status line
    static void PrintLiveStatus(CarbonEngine& engine);

    // Print future projection
    static void PrintProjection(CarbonEngine& engine, double futureHours);
};
