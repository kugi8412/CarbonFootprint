import pytest

from carbon_tracker import Activity, ActivityTracker


def test_factories_and_totals(tmp_path):
    t = ActivityTracker()
    t.add(Activity.driving(km=25, vehicle="petrol_car"))
    t.add(Activity.flight(km=800, flight_class="economy"))
    t.add(Activity.food("beef", kg=0.3))
    t.add(Activity.heating(kwh=50, fuel="natural_gas"))
    t.add(Activity.custom("Cement", co2_grams=5000))
    assert t.total_co2_grams() == pytest.approx(25 * 120 + 800 * 133 + 0.3 * 27000
                                                + 50 * 185 + 5000)
    assert set(t.by_category()) == {"transport", "food", "energy", "other"}
    assert "TOTAL" in t.report()

    path = tmp_path / "acts.json"
    t.save(str(path))
    back = ActivityTracker.load(str(path))
    assert back.total_co2_grams() == pytest.approx(t.total_co2_grams())
    assert ActivityTracker.from_dict_list(t.to_dict_list()).total_co2_kg() == pytest.approx(
        t.total_co2_kg())


def test_unknown_types_fall_back():
    assert Activity.driving(km=1, vehicle="spaceship").co2_grams == 120
    assert Activity.food("mystery", kg=1).co2_grams == 500
