import pytest
import requests

from carbon_tracker import carbon_api


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._data


@pytest.mark.parametrize("raw,zone", [
    ("pl", "PL"), (" de ", "DE"), ("us-mida", "US-MIDA-PJM"),
    ("US-CAL", "US-CAL-CISO"), ("CL", "CL-SEN"), ("", ""),
])
def test_normalize_zone(raw, zone):
    assert carbon_api.normalize_zone(raw) == zone


@pytest.mark.parametrize("zone,value", [
    ("PL", 589), ("GR", 315), ("US", 384), ("us-mida", 384), ("US-CAL-CISO", 384),
    ("CA-ON", 191), ("CL-SEN", 289), ("XX", 458),
])
def test_fallback_values(zone, value):
    assert carbon_api.get_fallback_intensity(zone) == value


def test_has_fallback():
    assert carbon_api.has_fallback_intensity("us-mida")
    assert not carbon_api.has_fallback_intensity("XX")


def test_ip_detection_skips_rate_limited_service_and_caches(monkeypatch):
    calls = []

    def fake_get(url, timeout=None, headers=None):
        calls.append(url)
        if "ipapi.co" in url:
            return FakeResponse({"error": True, "reason": "RateLimited"})
        return FakeResponse({"country": "pl", "city": "Warsaw"})

    monkeypatch.setattr(carbon_api.requests, "get", fake_get)
    assert carbon_api.auto_detect_zone() == ("PL", "Warsaw (PL)")
    n = len(calls)
    assert carbon_api.auto_detect_zone()[0] == "PL"
    assert len(calls) == n
    assert carbon_api.auto_detect_zone(refresh=True)[0] == "PL"
    assert len(calls) > n


def test_offline_detection_is_automatic(monkeypatch):
    def offline(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(carbon_api.requests, "get", offline)
    monkeypatch.setattr(carbon_api, "_windows_region_country", lambda: "")
    monkeypatch.setattr(carbon_api, "_timezone_country", lambda: "DE")
    monkeypatch.setattr(carbon_api, "_locale_country", lambda: "US")
    zone, desc = carbon_api.auto_detect_zone()
    assert zone == "DE"
    assert "offline" in desc and "--zone" not in desc


def test_offline_detection_nothing_known(monkeypatch):
    def offline(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(carbon_api.requests, "get", offline)
    for name in ("_windows_region_country", "_timezone_country", "_locale_country"):
        monkeypatch.setattr(carbon_api, name, lambda: "")
    assert carbon_api.auto_detect_zone() == ("", "")


def test_fetch_live_uses_valid_zone_id(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["url"] = url
        return FakeResponse({"carbonIntensity": 123})

    monkeypatch.setattr(carbon_api.requests, "get", fake_get)
    assert carbon_api.fetch_carbon_intensity("us-mida", "key") == (123.0, True)
    assert seen["url"].endswith("zone=US-MIDA-PJM")


def test_fetch_falls_back_on_error(monkeypatch):
    monkeypatch.setattr(carbon_api.requests, "get",
                        lambda *a, **k: FakeResponse({}, status=401))
    assert carbon_api.fetch_carbon_intensity("GR", "bad-key") == (315, False)


def test_no_request_without_api_key(monkeypatch):
    monkeypatch.setattr(carbon_api.requests, "get",
                        lambda *a, **k: pytest.fail("request sent without a key"))
    assert carbon_api.fetch_carbon_intensity("PL") == (589, False)
