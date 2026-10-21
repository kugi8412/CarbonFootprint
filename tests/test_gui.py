"""GUI tests, run headless (QT_QPA_PLATFORM=offscreen). Skipped without PyQt5."""

import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PyQt5.QtWidgets")

from carbon_tracker import gui  # noqa: E402
from carbon_tracker.globals import OTHER_APP_NAME  # noqa: E402
from carbon_tracker.project import CarbonProject  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture
def window(qapp, monkeypatch, tmp_path, hw, session):
    """Main window with dialogs, hardware and zone detection replaced."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gui, "detect_hardware", lambda: hw)
    monkeypatch.setattr(gui, "auto_detect_zone", lambda refresh=False: ("PL", "Test (PL)"))
    box = gui.QMessageBox
    monkeypatch.setattr(box, "information", staticmethod(lambda *a, **k: box.Ok))
    monkeypatch.setattr(box, "warning", staticmethod(lambda *a, **k: box.Ok))
    monkeypatch.setattr(box, "critical", staticmethod(
        lambda *a, **k: pytest.fail(f"error dialog: {a[1:]}")))
    monkeypatch.setattr(gui.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Wet Lab", True)))
    # the save dialog adds ".carbon.json" to a name ending in ".carbon"
    monkeypatch.setattr(gui.QFileDialog, "getSaveFileName", staticmethod(
        lambda *a, **k: (str(tmp_path / "Wet Lab.carbon.carbon.json"), "")))

    made = iter(session(f"g{i}", start=1_000 + i,
                        apps={"slack.exe": (3600, 0.03, 20), OTHER_APP_NAME: (3600, 0.05, 30)})
                for i in range(10))

    class FakeTracker:
        def __init__(self, **kwargs):
            self.apps = kwargs["apps"]
            self.zone = kwargs["zone"] or "PL"
            self.is_running = False

        def start(self):
            self.is_running = True

        def stop(self):
            self.is_running = False
            return next(made)

        def get_snapshot(self):
            return {
                "total_carbon_grams": 50.0, "total_energy_kwh": 0.08, "total_seconds": 3600,
                "intensity": 650, "intensity_real": False, "zone": self.zone,
                "power_estimated": True, "power_source": "est", "monitored_apps": self.apps,
                "apps": {
                    "slack.exe": {"total_energy_kwh": 0.03, "total_carbon_grams": 20.0,
                                  "total_active_seconds": 3600},
                    OTHER_APP_NAME: {"total_energy_kwh": 0.05, "total_carbon_grams": 30.0,
                                     "total_active_seconds": 3600},
                },
            }

        def add_app(self, name):
            pass

        def remove_app(self, name):
            pass

        def add_tab_filter(self, browser, keyword=None):
            pass

    monkeypatch.setattr(gui, "CarbonTracker", FakeTracker)
    w = gui.CarbonTrackerGUI()
    yield w
    w._timer.stop()
    w.deleteLater()


def _wait_for(qapp, cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_zone_detected_in_background_reaches_ui(qapp, window):
    assert _wait_for(qapp, lambda: "PL" in window._zone_label.text())
    assert window._zone_entry.text() == "PL"


def test_duplicate_app_names_are_merged(window):
    window._app_entry.setText("slack.exe")
    window._add_app()
    window._add_app_item("Slack.exe")
    window._add_app_item("SLACK")
    assert window._app_list.count() == 1


def test_project_sessions_go_to_one_file(qapp, window, tmp_path):
    _wait_for(qapp, lambda: window._zone_entry.text() == "PL")
    window._add_app_item("slack.exe")
    window._new_project()
    for _ in range(2):
        window._start_monitoring()
        window._update_dashboard()
        window._stop_monitoring()
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["Wet Lab.carbon.json"]
    p = CarbonProject.load(str(tmp_path / "Wet Lab.carbon.json"))
    assert len(p.sessions) == 2 and p.zone == "PL"


def test_dashboard_rows_sum_to_cards(window):
    window._add_app_item("slack.exe")
    window._start_monitoring()
    window._update_dashboard()
    tree = window._app_tree
    rows = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    names = [r.text(0) for r in rows]
    assert names[-1] == "Σ total" and names[-2] == OTHER_APP_NAME
    total = rows[-1]
    assert float(total.text(4)) == pytest.approx(50.0)
    assert float(total.text(3)) == pytest.approx(80.0)
    window._stop_monitoring()


def test_without_project_a_report_is_written(window, tmp_path):
    window._add_app_item("slack.exe")
    window._start_monitoring()
    window._stop_monitoring()
    assert [p.name for p in tmp_path.iterdir()][0].startswith("carbon_report_")


def test_forecast_and_import(qapp, window, tmp_path, monkeypatch, session):
    window._add_app_item("slack.exe")
    window._new_project()
    window._start_monitoring()
    window._stop_monitoring()

    report = tmp_path / "carbon_report_ext.json"
    report.write_text(json.dumps(session("ext", start=9_999).to_dict()), encoding="utf-8")
    monkeypatch.setattr(gui.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(report), "")))
    window._import_session_file()
    window._import_session_file()
    assert len(window.project.sessions) == 2

    window._do_forecast()
    text = window._history_text.toPlainText()
    assert "FORECAST for 8.0 hours" in text and "±" not in text


def test_opening_a_report_does_not_overwrite_it(window, tmp_path, monkeypatch, session):
    report = tmp_path / "carbon_report_x.json"
    report.write_text(json.dumps(session("x").to_dict()), encoding="utf-8")
    monkeypatch.setattr(gui.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(report), "")))
    window._open_project()
    assert window.project is not None and window.project_path is None
