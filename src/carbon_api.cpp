#include "carbon_api.h"

// ============================================================
// Carbon Intensity API Implementation
// ============================================================

CarbonAPI::CarbonAPI(const std::string& zone, const std::string& apiKey)
    : zone_(zone), apiKey_(apiKey) {
    lastData_.intensity = GetFallbackIntensity(zone_, TimeUtil::CurrentHour());
    lastData_.zone = zone_;
    lastData_.datetime = TimeUtil::Now();
    lastData_.isRealData = false;
}

void CarbonAPI::SetZone(const std::string& zone) {
    zone_ = zone;
    std::lock_guard<std::mutex> lock(dataMutex_);
    lastData_.intensity = GetFallbackIntensity(zone_, TimeUtil::CurrentHour());
    lastData_.zone = zone_;
    lastData_.isRealData = false;
}

std::string CarbonAPI::GetZone() const {
    return zone_;
}

// HTTP Request using platform-native or system curl

#ifdef PLATFORM_WINDOWS

std::string CarbonAPI::HttpGet(const std::string& url, const std::string& authHeader) {
    std::string result;

    // Parse URL to extract host and path
    // Expected format: https://host/path
    std::string host, path;
    size_t hostStart = url.find("://");
    if (hostStart == std::string::npos) return "";
    hostStart += 3;
    size_t pathStart = url.find('/', hostStart);
    if (pathStart == std::string::npos) {
        host = url.substr(hostStart);
        path = "/";
    } else {
        host = url.substr(hostStart, pathStart - hostStart);
        path = url.substr(pathStart);
    }

    // Convert to wide strings
    std::wstring wHost(host.begin(), host.end());
    std::wstring wPath(path.begin(), path.end());

    HINTERNET hSession = WinHttpOpen(L"CarbonTracker/1.0",
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession) return "";

    HINTERNET hConnect = WinHttpConnect(hSession, wHost.c_str(), INTERNET_DEFAULT_HTTPS_PORT, 0);
    if (!hConnect) { WinHttpCloseHandle(hSession); return ""; }

    HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET", wPath.c_str(),
        NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE);
    if (!hRequest) {
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return "";
    }

    // Add auth header if provided
    if (!authHeader.empty()) {
        std::wstring wHeader(authHeader.begin(), authHeader.end());
        WinHttpAddRequestHeaders(hRequest, wHeader.c_str(), (DWORD)-1, WINHTTP_ADDREQ_FLAG_ADD);
    }

    if (WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
            WINHTTP_NO_REQUEST_DATA, 0, 0, 0) &&
        WinHttpReceiveResponse(hRequest, NULL)) {

        DWORD dwSize = 0;
        DWORD dwDownloaded = 0;
        do {
            dwSize = 0;
            WinHttpQueryDataAvailable(hRequest, &dwSize);
            if (dwSize > 0) {
                std::vector<char> buffer(dwSize + 1, 0);
                WinHttpReadData(hRequest, buffer.data(), dwSize, &dwDownloaded);
                result.append(buffer.data(), dwDownloaded);
            }
        } while (dwSize > 0);
    }

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);
    return result;
}

#else // Linux / Mac

std::string CarbonAPI::HttpGet(const std::string& url, const std::string& authHeader) {
    // Use system curl command
    std::string cmd = "curl -s --max-time 10";
    if (!authHeader.empty()) {
        // Extract header value (format: "Header: value")
        cmd += " -H '" + authHeader + "'";
    }
    cmd += " '" + url + "' 2>/dev/null";

    FILE* pipe = popen(cmd.c_str(), "r");
    if (!pipe) return "";

    std::string result;
    char buffer[4096];
    while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
        result += buffer;
    }
    pclose(pipe);
    return result;
}

#endif

// Simple JSON value extraction
static std::string ExtractJsonValue(const std::string& json, const std::string& key) {
    std::string searchKey = "\"" + key + "\"";
    size_t pos = json.find(searchKey);
    if (pos == std::string::npos) return "";

    pos = json.find(':', pos + searchKey.size());
    if (pos == std::string::npos) return "";
    pos++;

    // Skip whitespace
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
    if (pos >= json.size()) return "";

    if (json[pos] == '"') {
        // String value
        size_t end = json.find('"', pos + 1);
        if (end == std::string::npos) return "";
        return json.substr(pos + 1, end - pos - 1);
    } else {
        // Numeric or other value
        size_t end = json.find_first_of(",}] \t\n\r", pos);
        if (end == std::string::npos) end = json.size();
        return json.substr(pos, end - pos);
    }
}

CarbonIntensityData CarbonAPI::ParseResponse(const std::string& json) {
    CarbonIntensityData data;
    data.zone = zone_;
    data.datetime = TimeUtil::Now();
    data.isRealData = false;

    std::string intensityStr = ExtractJsonValue(json, "carbonIntensity");
    if (intensityStr.empty()) {
        // Try alternative field names
        intensityStr = ExtractJsonValue(json, "value");
    }

    if (!intensityStr.empty()) {
        try {
            data.intensity = std::stod(intensityStr);
            data.isRealData = true;
        } catch (...) {
            data.intensity = GetFallbackIntensity(zone_, TimeUtil::CurrentHour());
        }
    } else {
        data.intensity = GetFallbackIntensity(zone_, TimeUtil::CurrentHour());
    }

    std::string dt = ExtractJsonValue(json, "datetime");
    if (!dt.empty()) data.datetime = dt;

    return data;
}

bool CarbonAPI::FetchLatest() {
    std::string url = "https://api.electricitymap.org/v3/carbon-intensity/latest?zone=" + zone_;
    std::string authHeader;
    if (!apiKey_.empty()) {
        authHeader = "auth-token: " + apiKey_;
    }

    std::string response = HttpGet(url, authHeader);
    if (response.empty()) {
        std::cerr << "[API] Failed to fetch carbon intensity data. Using fallback.\n";
        std::lock_guard<std::mutex> lock(dataMutex_);
        lastData_.intensity = GetFallbackIntensity(zone_, TimeUtil::CurrentHour());
        lastData_.isRealData = false;
        return false;
    }

    // Check for error response
    std::string errorMsg = ExtractJsonValue(response, "error");
    if (!errorMsg.empty()) {
        std::cerr << "[API] Error: " << errorMsg << ". Using fallback.\n";
        std::lock_guard<std::mutex> lock(dataMutex_);
        lastData_.intensity = GetFallbackIntensity(zone_, TimeUtil::CurrentHour());
        lastData_.isRealData = false;
        return false;
    }

    CarbonIntensityData data = ParseResponse(response);
    {
        std::lock_guard<std::mutex> lock(dataMutex_);
        lastData_ = data;
    }

    if (data.isRealData) {
        std::cout << "[API] Carbon intensity updated: " << data.intensity
                  << " gCO2eq/kWh (zone: " << data.zone << ")\n";
    }
    return data.isRealData;
}

CarbonIntensityData CarbonAPI::GetIntensity() {
    std::lock_guard<std::mutex> lock(dataMutex_);
    return lastData_;
}

double CarbonAPI::GetFallbackIntensity(const std::string& zone, int hour) {
    // Average carbon intensity by zone (gCO2eq/kWh)
    // Source: approximate values from electricitymap.org historical data
    struct ZoneData {
        double dayIntensity;    // 6:00-18:00 (more solar)
        double nightIntensity;  // 18:00-6:00 (more fossil)
    };

    static const std::map<std::string, ZoneData> zoneMap = {
        {"PL",      {650, 750}},   // Poland - coal-heavy
        {"DE",      {350, 450}},   // Germany - mixed
        {"FR",      {60, 80}},     // France - nuclear
        {"SE",      {25, 40}},     // Sweden - hydro/nuclear
        {"NO",      {20, 30}},     // Norway - hydro
        {"GB",      {200, 280}},   // UK - gas/wind
        {"ES",      {180, 250}},   // Spain - solar/wind
        {"IT",      {300, 380}},   // Italy - gas
        {"US-CAL",  {200, 300}},   // California - solar/gas
        {"US-NY",   {250, 320}},   // New York
        {"US-TEX",  {380, 450}},   // Texas - gas/wind
        {"US-MIDA", {400, 480}},   // Mid-Atlantic
        {"CN",      {550, 650}},   // China - coal
        {"IN",      {650, 720}},   // India - coal
        {"JP",      {450, 530}},   // Japan - gas/coal
        {"AU",      {550, 650}},   // Australia - coal
        {"BR",      {80, 120}},    // Brazil - hydro
        {"CA-ON",   {30, 50}},     // Ontario - nuclear/hydro
        {"CA-QC",   {10, 15}},     // Quebec - hydro
        {"DK",      {150, 250}},   // Denmark - wind
        {"FI",      {80, 120}},    // Finland - nuclear/hydro
        {"AT",      {100, 160}},   // Austria - hydro
        {"CH",      {30, 50}},     // Switzerland - hydro/nuclear
        {"CZ",      {450, 550}},   // Czech Republic - coal
        {"NL",      {350, 430}},   // Netherlands - gas
    };

    auto it = zoneMap.find(zone);
    ZoneData zd = (it != zoneMap.end()) ? it->second : ZoneData{400, 500};

    // Day = 6:00-18:00
    if (hour >= 6 && hour < 18) {
        return zd.dayIntensity;
    } else {
        return zd.nightIntensity;
    }
}

std::vector<std::pair<std::string, std::string>> CarbonAPI::GetCommonZones() {
    return {
        {"PL",      "Poland"},
        {"DE",      "Germany"},
        {"FR",      "France"},
        {"GB",      "United Kingdom"},
        {"SE",      "Sweden"},
        {"NO",      "Norway"},
        {"ES",      "Spain"},
        {"IT",      "Italy"},
        {"DK",      "Denmark"},
        {"NL",      "Netherlands"},
        {"CH",      "Switzerland"},
        {"AT",      "Austria"},
        {"CZ",      "Czech Republic"},
        {"FI",      "Finland"},
        {"US-CAL",  "USA - California"},
        {"US-NY",   "USA - New York"},
        {"US-TEX",  "USA - Texas"},
        {"US-MIDA", "USA - Mid-Atlantic"},
        {"CA-ON",   "Canada - Ontario"},
        {"CA-QC",   "Canada - Quebec"},
        {"JP",      "Japan"},
        {"CN",      "China"},
        {"IN",      "India"},
        {"AU",      "Australia"},
        {"BR",      "Brazil"},
    };
}

// ---- Auto-detect zone from IP geolocation ----

std::string CarbonAPI::CountryToZone(const std::string& countryCode) {
    static const std::map<std::string, std::string> countryZoneMap = {
        {"PL", "PL"}, {"DE", "DE"}, {"FR", "FR"}, {"GB", "GB"},
        {"SE", "SE"}, {"NO", "NO"}, {"ES", "ES"}, {"IT", "IT"},
        {"DK", "DK"}, {"NL", "NL"}, {"CH", "CH"}, {"AT", "AT"},
        {"CZ", "CZ"}, {"FI", "FI"}, {"PT", "PT"}, {"BE", "BE"},
        {"IE", "IE"}, {"RO", "RO"}, {"HU", "HU"}, {"SK", "SK"},
        {"HR", "HR"}, {"BG", "BG"}, {"LT", "LT"}, {"LV", "LV"},
        {"EE", "EE"}, {"SI", "SI"}, {"GR", "GR"},
        {"JP", "JP"}, {"CN", "CN"}, {"IN", "IN"},
        {"AU", "AU"}, {"BR", "BR"}, {"KR", "KR"},
        {"CA", "CA-ON"}, {"US", "US-MIDA"},
        {"MX", "MX"}, {"AR", "AR"}, {"CL", "CL"},
        {"ZA", "ZA"}, {"NZ", "NZ"}, {"TW", "TW"},
        {"SG", "SG"}, {"TH", "TH"}, {"MY", "MY"},
        {"ID", "ID"}, {"PH", "PH"}, {"VN", "VN"},
        {"UA", "UA"}, {"TR", "TR"}, {"IL", "IL"},
        {"SA", "SA"}, {"AE", "AE"}, {"EG", "EG"},
    };

    auto it = countryZoneMap.find(countryCode);
    if (it != countryZoneMap.end()) return it->second;
    return countryCode; // Use country code directly as fallback
}

std::string CarbonAPI::AutoDetectZone() {
    // Use ipapi.co (free, no key required, returns country code)
    CarbonAPI tempApi;

    std::string response = tempApi.HttpGet("https://ipapi.co/json/");
    if (!response.empty()) {
        std::string country = ExtractJsonValue(response, "country_code");
        if (!country.empty()) {
            std::string zone = CountryToZone(country);
            std::string city = ExtractJsonValue(response, "city");
            std::string region = ExtractJsonValue(response, "region");
            std::cout << "[GeoIP] Detected location: " << city
                      << (region.empty() ? "" : ", " + region)
                      << " (" << country << ") -> Zone: " << zone << "\n";
            return zone;
        }
    }

    // Fallback: try ip-api.com
    response = tempApi.HttpGet("https://ip-api.com/json/?fields=countryCode,city,regionName");
    if (!response.empty()) {
        std::string country = ExtractJsonValue(response, "countryCode");
        if (!country.empty()) {
            std::string zone = CountryToZone(country);
            std::string city = ExtractJsonValue(response, "city");
            std::cout << "[GeoIP] Detected location: " << city
                      << " (" << country << ") -> Zone: " << zone << "\n";
            return zone;
        }
    }

    std::cerr << "[GeoIP] Could not auto-detect location. Using default zone.\n";
    return "";
}
