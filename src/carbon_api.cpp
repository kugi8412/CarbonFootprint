#include "carbon_api.h"
#include <cctype>

// ============================================================
// Carbon Intensity API Implementation
// ============================================================

// Zones not in the table: world average (Ember, 2025)
static constexpr double kGlobalAverageIntensity = 458.0;

std::string CarbonAPI::NormalizeZone(const std::string& zone) {
    std::string z;
    for (unsigned char c : zone) {
        if (std::isalnum(c) || c == '-') z += static_cast<char>(std::toupper(c));
    }
    // Old codes that Electricity Maps does not accept
    static const std::map<std::string, std::string> aliases = {
        {"US-MIDA", "US-MIDA-PJM"}, {"US-CAL", "US-CAL-CISO"},
        {"US-NY", "US-NY-NYIS"}, {"US-TEX", "US-TEX-ERCO"}, {"CL", "CL-SEN"},
    };
    auto it = aliases.find(z);
    return it != aliases.end() ? it->second : z;
}

CarbonAPI::CarbonAPI(const std::string& zone, const std::string& apiKey)
    : zone_(NormalizeZone(zone)), apiKey_(apiKey) {
    lastData_.intensity = GetFallbackIntensity(zone_);
    lastData_.zone = zone_;
    lastData_.datetime = TimeUtil::Now();
    lastData_.isRealData = false;
}

void CarbonAPI::SetZone(const std::string& zone) {
    std::lock_guard<std::mutex> lock(dataMutex_);
    zone_ = NormalizeZone(zone);
    lastData_.intensity = GetFallbackIntensity(zone_);
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
    // Timeouts (ms): resolve, connect, send, receive
    WinHttpSetTimeouts(hSession, 5000, 5000, 10000, 10000);

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

    DWORD status = 0;
    DWORD statusSize = sizeof(status);
    if (WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
            WINHTTP_NO_REQUEST_DATA, 0, 0, 0) &&
        WinHttpReceiveResponse(hRequest, NULL) &&
        WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
            WINHTTP_HEADER_NAME_BY_INDEX, &status, &statusSize, WINHTTP_NO_HEADER_INDEX) &&
        status == 200) {

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
    // Arguments go into a single-quoted shell command
    for (const std::string* s : {&url, &authHeader}) {
        if (s->find_first_of("'\n\r") != std::string::npos) return "";
    }
    // Use system curl command
    std::string cmd = "curl -sf --max-time 10";
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
            data.intensity = GetFallbackIntensity(zone_);
        }
    } else {
        data.intensity = GetFallbackIntensity(zone_);
    }

    std::string dt = ExtractJsonValue(json, "datetime");
    if (!dt.empty()) data.datetime = dt;

    return data;
}

bool CarbonAPI::FetchLatest() {
    if (apiKey_.empty()) {
        // The Electricity Maps API answers only requests with a key
        std::lock_guard<std::mutex> lock(dataMutex_);
        lastData_.intensity = GetFallbackIntensity(zone_);
        lastData_.isRealData = false;
        return false;
    }
    std::string url = "https://api.electricitymap.org/v3/carbon-intensity/latest?zone=" + zone_;
    std::string authHeader;
    if (!apiKey_.empty()) {
        authHeader = "auth-token: " + apiKey_;
    }

    std::string response = HttpGet(url, authHeader);
    if (response.empty()) {
        std::cerr << "[API] Failed to fetch carbon intensity data. Using fallback.\n";
        std::lock_guard<std::mutex> lock(dataMutex_);
        lastData_.intensity = GetFallbackIntensity(zone_);
        lastData_.isRealData = false;
        return false;
    }

    // Check for error response
    std::string errorMsg = ExtractJsonValue(response, "error");
    if (!errorMsg.empty()) {
        std::cerr << "[API] Error: " << errorMsg << ". Using fallback.\n";
        std::lock_guard<std::mutex> lock(dataMutex_);
        lastData_.intensity = GetFallbackIntensity(zone_);
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

double CarbonAPI::GetFallbackIntensity(const std::string& zone) {
    // Lifecycle annual averages (gCO2eq/kWh) by country from Ember, Yearly
    // Electricity Data (via Our World in Data), 2025 or the latest year
    // available. Sub-national zones (US-CAL-CISO, CA-ON) use their country.
    static const std::map<std::string, double> countryIntensity = {
        {"AE", 468}, {"AR", 346}, {"AT", 117}, {"AU", 525}, {"BE", 150}, {"BG", 276},
        {"BR", 110}, {"CA", 191}, {"CH", 39}, {"CL", 289}, {"CN", 525}, {"CZ", 401},
        {"DE", 330}, {"DK", 114}, {"EE", 319}, {"EG", 563}, {"ES", 154}, {"FI", 57},
        {"FR", 41}, {"GB", 217}, {"GR", 315}, {"HR", 158}, {"HU", 163}, {"ID", 680},
        {"IE", 257}, {"IL", 493}, {"IN", 670}, {"IT", 285}, {"JP", 477}, {"KR", 417},
        {"LT", 138}, {"LV", 139}, {"MX", 474}, {"MY", 602}, {"NL", 254}, {"NO", 28},
        {"NZ", 93}, {"PH", 588}, {"PL", 589}, {"PT", 128}, {"RO", 251}, {"SA", 692},
        {"SE", 35}, {"SG", 497}, {"SI", 183}, {"SK", 95}, {"TH", 546}, {"TR", 475},
        {"TW", 633}, {"UA", 250}, {"US", 384}, {"VN", 461}, {"ZA", 699},
    };

    std::string z = NormalizeZone(zone);
    auto it = countryIntensity.find(z);
    if (it == countryIntensity.end()) it = countryIntensity.find(z.substr(0, z.find('-')));
    return it != countryIntensity.end() ? it->second : kGlobalAverageIntensity;
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
        {"US",          "USA (national average)"},
        {"US-CAL-CISO", "USA - California"},
        {"US-NY-NYIS",  "USA - New York"},
        {"US-TEX-ERCO", "USA - Texas"},
        {"US-MIDA-PJM", "USA - Mid-Atlantic"},
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
        {"CA", "CA"}, {"US", "US"},
        {"MX", "MX"}, {"AR", "AR"}, {"CL", "CL-SEN"},
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

// ---- Offline country guess ----

static std::string CountryFromTimeZone() {
    // IANA time zone -> country
    static const std::map<std::string, std::string> tzCountry = {
        {"Europe/Warsaw", "PL"}, {"Europe/Berlin", "DE"}, {"Europe/Paris", "FR"},
        {"Europe/London", "GB"}, {"Europe/Stockholm", "SE"}, {"Europe/Oslo", "NO"},
        {"Europe/Madrid", "ES"}, {"Europe/Rome", "IT"}, {"Europe/Copenhagen", "DK"},
        {"Europe/Amsterdam", "NL"}, {"Europe/Zurich", "CH"}, {"Europe/Vienna", "AT"},
        {"Europe/Prague", "CZ"}, {"Europe/Helsinki", "FI"}, {"Europe/Lisbon", "PT"},
        {"Europe/Brussels", "BE"}, {"Europe/Dublin", "IE"}, {"Europe/Bucharest", "RO"},
        {"Europe/Budapest", "HU"}, {"Europe/Bratislava", "SK"}, {"Europe/Zagreb", "HR"},
        {"Europe/Sofia", "BG"}, {"Europe/Athens", "GR"}, {"Europe/Vilnius", "LT"},
        {"Europe/Riga", "LV"}, {"Europe/Tallinn", "EE"}, {"Europe/Ljubljana", "SI"},
        {"Europe/Kyiv", "UA"}, {"Europe/Kiev", "UA"}, {"Europe/Istanbul", "TR"},
        {"Asia/Tokyo", "JP"}, {"Asia/Shanghai", "CN"}, {"Asia/Kolkata", "IN"},
        {"Asia/Seoul", "KR"}, {"Asia/Taipei", "TW"}, {"Asia/Singapore", "SG"},
        {"Australia/Sydney", "AU"}, {"Australia/Melbourne", "AU"},
        {"Pacific/Auckland", "NZ"}, {"America/Sao_Paulo", "BR"},
        {"America/Toronto", "CA"}, {"America/Mexico_City", "MX"},
        {"America/New_York", "US"}, {"America/Chicago", "US"},
        {"America/Denver", "US"}, {"America/Los_Angeles", "US"},
    };
    std::vector<std::string> names;
#ifndef PLATFORM_WINDOWS
    if (const char* tz = std::getenv("TZ")) names.push_back(tz[0] == ':' ? tz + 1 : tz);
    std::ifstream tzFile("/etc/timezone");
    std::string line;
    if (tzFile && std::getline(tzFile, line)) names.push_back(line);
    char link[512] = {};
    ssize_t n = readlink("/etc/localtime", link, sizeof(link) - 1);
    if (n > 0) {
        std::string target(link, static_cast<size_t>(n));
        size_t p = target.find("zoneinfo/");
        if (p != std::string::npos) names.push_back(target.substr(p + 9));
    }
#endif
    for (const auto& name : names) {
        auto it = tzCountry.find(name);
        if (it != tzCountry.end()) return it->second;
    }
    return "";
}

static std::string CountryFromLocale() {
#ifdef PLATFORM_WINDOWS
    return "";
#else
    // "pl_PL.UTF-8" -> "PL"
    for (const char* var : {"LC_ALL", "LC_MESSAGES", "LANG"}) {
        const char* v = std::getenv(var);
        if (!v) continue;
        std::string s(v);
        size_t u = s.find('_');
        if (u != std::string::npos && s.size() >= u + 3) {
            std::string c = s.substr(u + 1, 2);
            for (auto& ch : c) ch = static_cast<char>(std::toupper(static_cast<unsigned char>(ch)));
            return c;
        }
    }
    return "";
#endif
}

std::string CarbonAPI::AutoDetectZone() {
    CarbonAPI tempApi;

    // (url, country field)
    const std::pair<const char*, const char*> endpoints[] = {
        {"https://ipapi.co/json/", "country_code"},
        {"https://ipinfo.io/json", "country"},
        {"https://ipwho.is/", "country_code"},
    };
    for (const auto& [url, field] : endpoints) {
        std::string response = tempApi.HttpGet(url);
        if (response.empty()) continue;
        std::string country = ExtractJsonValue(response, field);
        if (country.size() != 2) continue;
        for (auto& ch : country) ch = static_cast<char>(std::toupper(static_cast<unsigned char>(ch)));
        std::string zone = CountryToZone(country);
        std::string city = ExtractJsonValue(response, "city");
        std::cout << "[GeoIP] Detected location: " << city
                  << " (" << country << ") -> Zone: " << zone << "\n";
        return zone;
    }

    // Offline: Windows region setting, then time zone, then locale.
    std::string country, source;
#ifdef PLATFORM_WINDOWS
    char iso2[8] = {};
    if (GetGeoInfoA(GetUserGeoID(GEOCLASS_NATION), GEO_ISO2, iso2, sizeof(iso2), 0) > 0) {
        country = iso2;
        source = "region setting";
    }
#endif
    if (country.empty()) { country = CountryFromTimeZone(); source = "time zone"; }
    if (country.empty()) { country = CountryFromLocale(); source = "locale"; }
    if (!country.empty()) {
        std::string zone = CountryToZone(country);
        std::cout << "[GeoIP] Offline: zone " << zone << " from the " << source << ".\n";
        return zone;
    }

    std::cerr << "[GeoIP] Could not auto-detect location. Using default zone.\n";
    return "";
}
