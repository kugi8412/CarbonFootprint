import math

import pytest

from carbon_tracker.forecast import GaussianMixture1D, forecast_project
from carbon_tracker.project import CarbonProject


def test_bucket_rate_uses_real_bucket_length(session):
    s = session(seconds=900, grams=3, kwh=0.004, buckets={17: (900, 0.004, 3)})
    assert forecast_project([s], 1)["rate_grams_per_hour"] == pytest.approx(12)


def test_short_buckets_are_skipped(session):
    s = session(seconds=3604, grams=100.04, kwh=0.2,
                buckets={17: (4, 0.0001, 0.04), 18: (3600, 0.2, 100)})
    assert forecast_project([s], 1)["rate_grams_per_hour"] == pytest.approx(100)


def test_legacy_session_uses_its_average(session):
    s = session(seconds=7200, grams=100, kwh=0.15)  # no seconds_by_hour
    f = forecast_project([s], 4)
    assert f["rate_grams_per_hour"] == pytest.approx(50)
    assert f["projected_carbon_grams"] == pytest.approx(200)


@pytest.mark.parametrize("hours", [0, -5, float("nan")])
def test_non_positive_hours_project_nothing(session, hours):
    f = forecast_project([session()], hours)
    assert f["method"] == "none"
    assert f["projected_carbon_grams"] == 0


def test_never_negative_even_with_corrupt_samples(session):
    bad = session(buckets={1: (3600, -5, -100), 2: (3600, 0.1, float("nan")),
                           3: (3600, 0.1, 40)})
    f = forecast_project([bad], 8)
    for key in ("projected_carbon_grams", "carbon_low_grams", "carbon_high_grams",
                "projected_energy_kwh", "energy_low_kwh", "energy_high_kwh"):
        assert f[key] >= 0 and math.isfinite(f[key]), key


def test_per_app_forecast_has_clipped_range(session):
    s = session(apps={"code.exe": (3600, 0.05, 30), "slack.exe": (3600, 0.01, 1)})
    per_app = forecast_project([s], 2)["per_app"]
    assert per_app["code.exe"]["projected_carbon_grams"] == pytest.approx(60)
    assert all(v["carbon_low_grams"] >= 0 for v in per_app.values())


def test_gmm_finds_two_modes():
    gmm = GaussianMixture1D().fit([10, 11, 9, 10, 100, 101, 99, 100, 10, 100])
    # a mode may be split into several components
    low = sum(c["weight"] for c in gmm.components() if c["rate"] < 50)
    high = sum(c["weight"] for c in gmm.components() if c["rate"] >= 50)
    assert low == pytest.approx(0.5, abs=0.01) and high == pytest.approx(0.5, abs=0.01)
    assert gmm.mean() == pytest.approx(55, abs=1)


def test_project_falls_back_to_average_for_tiny_sessions(session):
    p = CarbonProject("tiny")
    p.add_session(session(seconds=4, grams=0.5, kwh=0.001))
    f = p.project_future(10)
    assert f["method"] == "average"
    assert f["projected_carbon_grams"] == pytest.approx(0.5 / (4 / 3600) * 10)


def test_project_future_negative_hours(session):
    p = CarbonProject("p")
    p.add_session(session())
    assert p.project_future(-1)["projected_carbon_grams"] == 0
