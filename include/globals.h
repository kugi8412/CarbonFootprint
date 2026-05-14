#pragma once

// ============================================================
// Global Constants and Configuration
// Mirrors globals.py from the Python version
// ============================================================

namespace Globals {

// ============================================================
// Assumptions and constants for calculations, projections, and UI
// ============================================================

constexpr double SECONDS_PER_HOUR = 3600.0;
constexpr double WATTS_PER_KW = 1000.0;
constexpr double PERCENT_MAX = 100.0;

constexpr double MIN_HOURS_EPSILON = 0.001;

constexpr int API_UPDATE_INTERVAL_SEC = 900;
constexpr double API_SLEEP_TICK_SEC = 1.0;

constexpr double CPU_POWER_CURVE_EXPONENT = 1.4;
constexpr double CPU_IDLE_FRACTION = 0.10;
constexpr double GPU_IDLE_FRACTION = 0.15;
constexpr double PROJECTION_CPU_LOAD_ESTIMATE = 0.30;

constexpr double MIN_SYSTEM_CPU_NOISE = 0.1;
constexpr double ACTIVE_APP_ENERGY_TAX = 0.10;
constexpr double BACKGROUND_APP_ENERGY_TAX = 0.02;

// ============================================================
// EMISSION FACTORS
// https://ourworldindata.org/environmental-impacts-of-food
// https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting
// ============================================================

// Vehicles: gCO2 per km
struct VehicleFactor {
    const char* name;
    double gCO2perKm;
};

inline const VehicleFactor VEHICLE_FACTORS[] = {
    {"petrol_car",      120.0},
    {"diesel_car",      132.0},
    {"hybrid_car",       76.0},
    {"electric_car",     50.0},
    {"motorcycle",       72.0},
    {"bus",              27.0},
    {"train",             6.0},
    {"tram",              5.0},
    {"scooter_electric", 16.0},
    {"bicycle",           0.0},
    {"walking",           0.0},
};
constexpr int VEHICLE_FACTORS_COUNT = sizeof(VEHICLE_FACTORS) / sizeof(VEHICLE_FACTORS[0]);

// Flights: gCO2 per passenger-km
struct FlightFactor {
    const char* classType;
    double gCO2perKm;
};

inline const FlightFactor FLIGHT_FACTORS[] = {
    {"economy",         133.0},
    {"premium_economy", 170.0},
    {"business",        234.0},
    {"first",           300.0},
};
constexpr int FLIGHT_FACTORS_COUNT = sizeof(FLIGHT_FACTORS) / sizeof(FLIGHT_FACTORS[0]);

// Food: gCO2 per kg of food
struct FoodFactor {
    const char* name;
    double gCO2perKg;
};

inline const FoodFactor FOOD_FACTORS[] = {
    {"beef",       27000.0},
    {"lamb",       25000.0},
    {"pork",        7000.0},
    {"chicken",     4300.0},
    {"fish",        3500.0},
    {"cheese",      8500.0},
    {"milk",        1200.0},
    {"eggs",        3200.0},
    {"rice",        1200.0},
    {"bread",        800.0},
    {"vegetables",   300.0},
    {"fruit",        400.0},
    {"tofu",         700.0},
    {"nuts",         800.0},
    {"coffee",      5000.0},
};
constexpr int FOOD_FACTORS_COUNT = sizeof(FOOD_FACTORS) / sizeof(FOOD_FACTORS[0]);

// Heating/cooling: gCO2 per kWh of fuel
struct EnergyFactor {
    const char* source;
    double gCO2perKwh;
};

inline const EnergyFactor ENERGY_FACTORS[] = {
    {"natural_gas",      185.0},
    {"heating_oil",      265.0},
    {"coal",             340.0},
    {"wood_pellets",      25.0},
    {"electricity",      400.0},
    {"district_heating", 130.0},
};
constexpr int ENERGY_FACTORS_COUNT = sizeof(ENERGY_FACTORS) / sizeof(ENERGY_FACTORS[0]);

// Miscellaneous: gCO2 per unit
struct MiscFactor {
    const char* name;
    double gCO2perUnit;
};

inline const MiscFactor MISC_FACTORS[] = {
    {"paper_kg",         920.0},
    {"plastic_kg",      6000.0},
    {"clothing_item",   8000.0},
    {"smartphone_unit", 70000.0},
    {"laptop_unit",    300000.0},
};
constexpr int MISC_FACTORS_COUNT = sizeof(MISC_FACTORS) / sizeof(MISC_FACTORS[0]);

} // namespace Globals
