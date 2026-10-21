"""Shared fixtures. No test touches the network or real power sensors."""

import pytest

import carbon_tracker
from carbon_tracker import carbon_api
from carbon_tracker.models import HardwareInfo, SessionData, AppUsageData


def pytest_report_header(config):
    return f"carbon_tracker {carbon_tracker.__version__} from {carbon_tracker.__file__}"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Keep tests offline: geolocation / Electricity Maps calls fail as if
    there were no connection (tests that need a response patch it)."""

    def _blocked(*args, **kwargs):
        raise carbon_api.requests.ConnectionError(f"network blocked in tests: {args[:1]}")

    monkeypatch.setattr(carbon_api.requests, "get", _blocked)
    carbon_api._zone_cache.clear()
    yield
    carbon_api._zone_cache.clear()


@pytest.fixture
def hw():
    return HardwareInfo(
        cpu_name="Test CPU", cpu_tdp_watts=28.0, cpu_cores=4,
        gpu_name="", gpu_tdp_watts=25.0, is_laptop=True, base_system_watts=15.0,
    )


@pytest.fixture
def session():
    """Factory for SessionData objects (see make_session)."""
    return make_session


def make_session(session_id="s1", start=1_000.0, seconds=3600.0, grams=50.0,
                 kwh=0.08, zone="PL", buckets=None, apps=None):
    """A session; ``buckets`` = {hour: (seconds, kwh, grams)}."""
    s = SessionData(
        session_id=session_id, start_time=start, end_time=start + seconds,
        duration_seconds=seconds, total_carbon_grams=grams, total_energy_kwh=kwh,
        zone=zone, avg_intensity=grams / kwh if kwh else 0.0,
    )
    for hour, (secs, e, g) in (buckets or {}).items():
        s.seconds_by_hour[hour] = secs
        s.energy_by_hour[hour] = e
        s.carbon_by_hour[hour] = g
    for name, (secs, e, g) in (apps or {}).items():
        s.apps[name] = AppUsageData(
            app_name=name, total_active_seconds=secs, total_energy_kwh=e,
            total_carbon_grams=g,
        )
    return s
