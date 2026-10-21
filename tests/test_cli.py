import json
import sys

import pytest

import carbon_tracker
from carbon_tracker import cli
from carbon_tracker.globals import OTHER_APP_NAME
from carbon_tracker.project import CarbonProject


def run_cli(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["carbon-tracker", *args])
    code = 0
    try:
        cli.main()
    except SystemExit as e:
        code = e.code or 0
    out = capsys.readouterr()
    return code, out.out + out.err


def test_version(monkeypatch, capsys):
    code, out = run_cli(monkeypatch, capsys, "--version")
    assert code == 0 and carbon_tracker.__version__ in out


def test_no_command_prints_help(monkeypatch, capsys):
    code, out = run_cli(monkeypatch, capsys)
    assert code == 0 and "monitor" in out and "project" in out


def test_project_workflow(monkeypatch, capsys, tmp_path, session):
    proj = str(tmp_path / "wet.carbon.json")
    code, out = run_cli(monkeypatch, capsys, "project", "create", proj,
                        "--name", "Wet Lab", "--zone", "PL")
    assert code == 0 and CarbonProject.load(proj).zone == "PL"

    report = tmp_path / "carbon_report_1.json"
    report.write_text(json.dumps(session("r1").to_dict()), encoding="utf-8")
    _, out = run_cli(monkeypatch, capsys, "project", "add-session", proj, "--session", str(report))
    assert "Added 1 session" in out
    _, out = run_cli(monkeypatch, capsys, "project", "add-session", proj, "--session", str(report))
    assert "already present" in out

    _, out = run_cli(monkeypatch, capsys, "project", "add-session", proj,
                     "--duration", "3600", "--carbon", "12.5", "--energy", "35")
    assert "Added 1 session" in out
    p = CarbonProject.load(proj)
    assert len(p.sessions) == 2
    assert p.sessions[1].total_energy_kwh == pytest.approx(0.035)

    _, out = run_cli(monkeypatch, capsys, "project", "add-session", proj,
                     "--duration", "-1", "--carbon", "1")
    assert "must be > 0" in out

    _, out = run_cli(monkeypatch, capsys, "project", "forecast", proj, "--hours", "-3")
    assert "--hours must be > 0" in out
    _, out = run_cli(monkeypatch, capsys, "project", "forecast", proj, "--hours", "8")
    assert "Forecast for 8.0 hours" in out and "±" not in out

    _, out = run_cli(monkeypatch, capsys, "project", "info", proj)
    assert "Wet Lab" in out and "Sessions:     2" in out


def test_hpc_report_and_validation(monkeypatch, capsys, tmp_path):
    out_file = tmp_path / "job.carbon.json"
    code, out = run_cli(monkeypatch, capsys, "hpc", "report", "--cpus", "4", "--elapsed",
                        "3600", "--zone", "PL", "--no-sacct", "--output", str(out_file))
    assert code == 0 and "MANUAL COMPUTATION WORKSHEET" in out
    assert json.loads(out_file.read_text())["type"] == "hpc_job_report"

    code, out = run_cli(monkeypatch, capsys, "hpc", "report", "--cpus", "4", "--elapsed",
                        "60", "--zone", "PL", "--no-sacct", "--cpu-util", "1.14")
    assert code == 2 and "cpu_utilization must be in (0, 1]" in out


def test_hpc_run_propagates_exit_code(monkeypatch, capsys):
    code, out = run_cli(monkeypatch, capsys, "hpc", "run", "--zone", "PL", "--no-sacct",
                        "--", sys.executable, "-c", "import sys; sys.exit(5)")
    assert code == 5 and "exited with code 5" in out


def test_monitor_rejects_bad_interval(monkeypatch, capsys):
    code, out = run_cli(monkeypatch, capsys, "monitor", "--app", "x.exe", "--interval", "0")
    assert "--interval must be > 0" in out


def test_monitor_saves_into_one_project(monkeypatch, capsys, tmp_path, session, hw):
    sessions = iter([session("m1", start=1_000), session("m2", start=2_000)])

    class FakeTracker:
        def __init__(self, apps, zone, api_key, update_interval):
            self.zone, self.hardware, self.apps = zone or "PL", hw, apps

        def start(self):
            pass

        def stop(self):
            return next(sessions)

        def get_snapshot(self):
            return {"total_seconds": 0, "total_carbon_grams": 0, "total_energy_kwh": 0,
                    "intensity": 650, "intensity_real": False, "power_estimated": True,
                    "power_source": "est"}

        def power_warning(self):
            return None

    def stop_after_first_sleep(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "CarbonTracker", FakeTracker)
    monkeypatch.setattr(cli.time, "sleep", stop_after_first_sleep)
    monkeypatch.chdir(tmp_path)
    proj = str(tmp_path / "p.carbon.json")
    for _ in range(2):
        run_cli(monkeypatch, capsys, "monitor", "--app", "x.exe", "--project", proj)
    files = sorted(f.name for f in tmp_path.iterdir())
    assert files == ["p.carbon.json"]
    p = CarbonProject.load(proj)
    assert [s.session_id for s in p.sessions] == ["m1", "m2"] and p.zone == "PL"


def test_gui_entry_point_without_pyqt(monkeypatch, capsys):
    # submodules too, test_gui.py may have imported them already
    for mod in ("PyQt5", "PyQt5.QtWidgets", "PyQt5.QtCore", "PyQt5.QtGui"):
        monkeypatch.setitem(sys.modules, mod, None)
    monkeypatch.delitem(sys.modules, "carbon_tracker.gui", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.gui_main()
    assert exc.value.code == 1
    assert 'pip install "carbon-footprint-tracker[gui]"' in capsys.readouterr().out


def test_other_row_name_is_not_a_process_name():
    assert "(" in OTHER_APP_NAME and ".exe" not in OTHER_APP_NAME
