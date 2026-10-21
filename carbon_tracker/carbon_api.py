#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Carbon intensity API: auto-detect zone + fetch real-time grid data.
"""

import os
import requests
import locale
import platform
import warnings

from typing import Tuple

from carbon_tracker.globals import (
    _COUNTRY_TO_ZONE,
    _FALLBACK_INTENSITY,
    _TIMEZONE_TO_COUNTRY,
    _ZONE_ALIASES,
    FALLBACK_GLOBAL_INTENSITY,
)

# (url, country field)
_GEO_ENDPOINTS = [
    ("https://ipapi.co/json/", "country_code"),
    ("https://ipinfo.io/json", "country"),
    ("https://ipwho.is/", "country_code"),
]

# Detected zone, reused for the rest of the process
_zone_cache: dict = {}


def normalize_zone(zone: str) -> str:
    """Upper-case zone ID; old codes are mapped to Electricity Maps IDs."""
    zone = (zone or "").strip().upper()
    return _ZONE_ALIASES.get(zone, zone)


def _table_key(zone: str) -> str:
    zone = normalize_zone(zone)
    return zone if zone in _FALLBACK_INTENSITY else zone.split("-")[0]


def has_fallback_intensity(zone: str) -> bool:
    """True when the offline table has a value for this zone (or its country)."""
    return _table_key(zone) in _FALLBACK_INTENSITY


def get_fallback_intensity(zone: str) -> float:
    """Annual average intensity for a zone; sub-national zones use their
    country's value, unknown zones the world average."""
    return float(_FALLBACK_INTENSITY.get(_table_key(zone), FALLBACK_GLOBAL_INTENSITY))


def _windows_region_country() -> str:
    """ISO-2 country of the Windows "Country or region" setting, or ""."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        geo_id = kernel32.GetUserGeoID(16)  # GEOCLASS_NATION
        buf = ctypes.create_unicode_buffer(8)
        if kernel32.GetGeoInfoW(geo_id, 4, buf, len(buf), 0):  # GEO_ISO2
            return buf.value.strip().upper()
    except Exception:
        pass
    return ""


def _timezone_country() -> str:
    """Country of the IANA time zone (TZ, /etc/timezone, /etc/localtime), or ""."""
    names = [os.environ.get("TZ", "").lstrip(":")]
    try:
        with open("/etc/timezone") as f:
            names.append(f.read().strip())
    except OSError:
        pass
    try:
        link = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in link:
            names.append(link.split("zoneinfo/", 1)[1])
    except OSError:
        pass
    for name in names:
        if name in _TIMEZONE_TO_COUNTRY:
            return _TIMEZONE_TO_COUNTRY[name]
    return ""


def _locale_country() -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            code = locale.getdefaultlocale()[0] or ""
    except Exception:
        code = ""
    # Locale looks like "pl_PL", "en_GB", "en_US".
    return code.split("_", 1)[1].upper()[:2] if "_" in code else ""


def _local_zone_guess() -> Tuple[str, str]:
    """Zone guess without network: Windows region setting, time zone, locale.

    Returns (zone_code, description) or ("", "").
    """
    sources = []
    if platform.system() == "Windows":
        sources.append(("region setting", _windows_region_country))
    sources.append(("time zone", _timezone_country))
    sources.append(("locale", _locale_country))
    for label, fn in sources:
        country = fn()
        if country and country in _COUNTRY_TO_ZONE:
            zone = _COUNTRY_TO_ZONE[country]
            return zone, f"{country} (offline, from {label})"
    return "", ""


def auto_detect_zone(refresh: bool = False) -> Tuple[str, str]:
    """
    Auto-detect electricity zone from IP geolocation.

    Falls back to an offline guess when the network is unavailable. Returns
    (zone_code, description); the zone is "" only when nothing can be resolved.
    The result is cached for the process; pass ``refresh=True`` to detect again.
    """
    if _zone_cache and not refresh:
        return _zone_cache["zone"], _zone_cache["desc"]

    for url, field in _GEO_ENDPOINTS:
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            country = (data.get(field) or "").upper()
            city = data.get("city", "")
            if country:
                zone = _COUNTRY_TO_ZONE.get(country, country)
                desc = f"{city} ({country})"
                _zone_cache.update(zone=zone, desc=desc)
                return zone, desc
        except Exception:
            continue

    # Offline / blocked network: fall back to the local guess.
    zone, desc = _local_zone_guess()
    if zone:
        _zone_cache.update(zone=zone, desc=desc)
    return zone, desc


def fetch_carbon_intensity(zone: str, api_key: str = "") -> Tuple[float, bool]:
    """
    Fetch live carbon intensity from Electricity Maps API.
    Returns (intensity_gCO2_per_kWh, is_real_data).

    When ``zone`` is empty (detection failed) a neutral global-average
    estimate is used instead of crashing.
    """
    zone = normalize_zone(zone)
    if not zone or not api_key:
        # The Electricity Maps API answers only requests with a key.
        return get_fallback_intensity(zone), False

    try:
        url = f"https://api.electricitymap.org/v3/carbon-intensity/latest?zone={zone}"
        resp = requests.get(url, headers={"auth-token": api_key}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        intensity = data.get("carbonIntensity") or data.get("value")

        if intensity is not None:
            return float(intensity), True

    except Exception:
        pass

    return get_fallback_intensity(zone), False
