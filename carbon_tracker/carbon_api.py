#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Carbon intensity API: auto-detect zone + fetch real-time grid data.
"""

import requests
import time

from typing import Tuple

from carbon_tracker.globals import _COUNTRY_TO_ZONE, _FALLBACK_INTENSITY


def get_fallback_intensity(zone: str) -> float:
    """Get estimated intensity for a zone based on time of day."""
    hour = time.localtime().tm_hour
    day_val, night_val = _FALLBACK_INTENSITY.get(zone, (400, 500))
    return day_val if 6 <= hour < 18 else night_val


def auto_detect_zone() -> Tuple[str, str]:
    """
    Auto-detect electricity zone from IP geolocation.
    Returns (zone_code, description) or ("", "") on failure.
    """
    for url in [
        "https://ipapi.co/json/",
        "https://ip-api.com/json/?fields=countryCode,city,regionName",
    ]:
        try:
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            country = data.get("country_code") or data.get("countryCode", "")
            city = data.get("city", "")
            if country:
                zone = _COUNTRY_TO_ZONE.get(country, country)
                return zone, f"{city} ({country})"
        except Exception:
            continue
    return "", ""


def fetch_carbon_intensity(zone: str, api_key: str = "") -> Tuple[float, bool]:
    """
    Fetch live carbon intensity from Electricity Maps API.
    Returns (intensity_gCO2_per_kWh, is_real_data).
    """
    try:
        url = f"https://api.electricitymap.org/v3/carbon-intensity/latest?zone={zone}"
        headers = {}
        if api_key:
            headers["auth-token"] = api_key
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        intensity = data.get("carbonIntensity") or data.get("value")

        if intensity is not None:
            return float(intensity), True

    except Exception:
        pass

    return get_fallback_intensity(zone), False
