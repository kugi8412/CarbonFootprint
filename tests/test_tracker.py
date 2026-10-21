import math
import time

import pytest

from carbon_tracker import tracker as T
from carbon_tracker.globals import OTHER_APP_NAME
from carbon_tracker.models import BrowserTabFilter


@pytest.fixture
def quiet(monkeypatch):
    """No sensors, no subprocesses, offline intensity table."""
    monkeypatch.setattr(T, "read_battery_status", lambda: {})
    monkeypatch.setattr(T, "read_cpu_power_watts", lambda: (None, None))
    monkeypatch.setattr(T, "read_gpu_power_draw", lambda: None)
    monkeypatch.setattr(T, "read_system_power_watts", lambda: (None, None))
    monkeypatch.setattr(
        T, "fetch_carbon_intensity",
        lambda zone, api_key="": (T.get_fallback_intensity(zone), False),
    )
    monkeypatch.setattr(T, "_get_active_window_process", lambda: ("a.exe", "title"))


def _fake_cpu(monkeypatch, system, per_app, running=("a", "b")):
    monkeypatch.setattr(T.psutil, "cpu_percent", lambda interval=0: system)
    monkeypatch.setattr(
        T, "_scan_processes_cached",
        lambda names, cache, wsl: ({n: per_app.get(T._app_key(n), 0.0) for n in names},
                                   set(running)),
    )


def _run(tr, seconds=0.5):
    tr._ncpu = 8
    tr.start()
    time.sleep(seconds)
    return tr.stop()


def _assert_rows_sum(s):
    assert s.total_energy_kwh > 0
    assert math.isclose(sum(a.total_energy_kwh for a in s.apps.values()),
                        s.total_energy_kwh, rel_tol=1e-9)
    assert math.isclose(sum(a.total_carbon_grams for a in s.apps.values()),
                        s.total_carbon_grams, rel_tol=1e-9)
    assert s.unattributed() == pytest.approx((0.0, 0.0), abs=1e-12)


def test_app_names_are_deduplicated(hw):
    tr = T.CarbonTracker(apps=["Slack.exe", "slack", "SLACK.EXE", "code.exe"],
                         zone="PL", hardware=hw)
    assert tr.apps == ["Slack.exe", "code.exe"]
    tr.add_app("CODE")
    assert tr.apps == ["Slack.exe", "code.exe"]


def test_zone_is_normalised(hw):
    assert T.CarbonTracker(zone="us-mida", hardware=hw).zone == "US-MIDA-PJM"


def test_multithreaded_app_cannot_exceed_total(quiet, monkeypatch, hw):
    # 400 % = 4 of 8 cores, while system CPU reads 10 %
    _fake_cpu(monkeypatch, system=10.0, per_app={"a": 400.0})
    s = _run(T.CarbonTracker(apps=["a.exe", "b.exe"], zone="PL", hardware=hw,
                             update_interval=0.05))
    _assert_rows_sum(s)
    assert s.apps["a.exe"].total_energy_kwh <= s.total_energy_kwh * (1 + 1e-9)


def test_busy_apps_share_and_other_row(quiet, monkeypatch, hw):
    _fake_cpu(monkeypatch, system=50.0, per_app={"a": 80.0, "b": 80.0})
    s = _run(T.CarbonTracker(apps=["a.exe", "b.exe"], zone="PL", hardware=hw,
                             update_interval=0.05))
    _assert_rows_sum(s)
    # each 80/8 = 10 % of the machine out of 50 % busy -> 20 %, other 60 %
    assert s.apps["a.exe"].total_energy_kwh / s.total_energy_kwh == pytest.approx(0.2)
    assert s.apps[OTHER_APP_NAME].total_energy_kwh / s.total_energy_kwh == pytest.approx(0.6)


def test_idle_floors_go_to_this_app_only(quiet, monkeypatch, hw):
    _fake_cpu(monkeypatch, system=0.0, per_app={})
    s = _run(T.CarbonTracker(apps=["a.exe", "b.exe"], zone="PL", hardware=hw,
                             update_interval=0.05))
    _assert_rows_sum(s)
    share = {k: v.total_energy_kwh / s.total_energy_kwh for k, v in s.apps.items()}
    assert share["a.exe"] == pytest.approx(0.10)  # foreground
    assert share["b.exe"] == pytest.approx(0.02)  # background


def test_duration_and_intensity(quiet, monkeypatch, hw):
    _fake_cpu(monkeypatch, system=20.0, per_app={"a": 10.0})
    t0 = time.monotonic()
    s = _run(T.CarbonTracker(apps=["a.exe"], zone="GR", hardware=hw,
                             update_interval=0.05), seconds=0.6)
    wall = time.monotonic() - t0
    assert 0.3 < s.duration_seconds <= wall + 0.1
    assert s.avg_intensity == pytest.approx(s.total_carbon_grams / s.total_energy_kwh)
    assert s.avg_intensity == pytest.approx(315)
    assert sum(s.seconds_by_hour.values()) == pytest.approx(s.duration_seconds)


def test_tab_filter_any_keyword(hw):
    tr = T.CarbonTracker(zone="PL", hardware=hw)
    tr.add_tab_filter("firefox.exe", "YouTube")
    tr.add_tab_filter(BrowserTabFilter("Firefox.exe", "Spotify"))
    assert tr._matches_tab_filter("firefox.exe", "Spotify - Web Player")
    assert tr._matches_tab_filter("firefox", "YouTube - Mozilla Firefox")
    assert not tr._matches_tab_filter("firefox.exe", "GitHub")
    assert not tr._matches_tab_filter("firefox.exe", "")
    assert tr._matches_tab_filter("code.exe", "anything")


def test_projection_without_data(hw):
    proj = T.CarbonTracker(zone="PL", hardware=hw).project_future(2)
    assert proj.projected_carbon_grams > 0
