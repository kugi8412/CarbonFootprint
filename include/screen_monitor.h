#pragma once
#include "platform.h"

// ============================================================
// Screen Monitor - Detects screen brightness
// ============================================================

class ScreenMonitor {
public:
    // Returns brightness as 0.0 to 1.0 (0% to 100%)
    // Returns -1.0 if detection not available
    static double GetBrightness();

    // Estimate screen power consumption in Watts based on brightness
    static double EstimateScreenPower(double brightness, bool isLaptop = true);
};
