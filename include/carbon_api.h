#pragma once
#include "platform.h"

// ============================================================
// Carbon Intensity API - Fetches real-time grid carbon intensity
// ============================================================

struct CarbonIntensityData {
    double intensity;         // gCO2eq/kWh
    std::string zone;
    std::string datetime;
    bool isRealData;
};

class CarbonAPI {
private:
    std::string zone_;
    std::string apiKey_;
    CarbonIntensityData lastData_;
    std::mutex dataMutex_;

    // HTTP request helper
    std::string HttpGet(const std::string& url, const std::string& authHeader = "");

    // Parse JSON response
    CarbonIntensityData ParseResponse(const std::string& json);

    // Fallback values by region when API is unavailable
    static double GetFallbackIntensity(const std::string& zone, int hour);

    // Map country code to electricity zone
    static std::string CountryToZone(const std::string& countryCode);

public:
    CarbonAPI(const std::string& zone = "PL", const std::string& apiKey = "");

    // Fetch latest carbon intensity from Electricity Maps API
    bool FetchLatest();

    // Get current carbon intensity (thread-safe)
    CarbonIntensityData GetIntensity();

    // Set region zone
    void SetZone(const std::string& zone);

    // Get zone
    std::string GetZone() const;

    // Auto-detect country/zone from IP geolocation
    static std::string AutoDetectZone();

    // List of common zones
    static std::vector<std::pair<std::string, std::string>> GetCommonZones();
};
