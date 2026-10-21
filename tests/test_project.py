import json
import os

import pytest

from carbon_tracker.activities import Activity
from carbon_tracker.models import SessionData
from carbon_tracker.project import CarbonProject, normalize_project_path


@pytest.mark.parametrize("path,expected", [
    ("a.carbon.carbon.json", "a.carbon.json"),
    ("a.carbon", "a.carbon.json"),
    ("a", "a.carbon.json"),
    ("a.carbon.json", "a.carbon.json"),
    ("A.CARBON.JSON", "A.carbon.json"),
])
def test_normalize_project_path(path, expected):
    assert normalize_project_path(path) == expected


def test_constructor_accepts_zone():
    assert CarbonProject("p", "d", zone="DE").zone == "DE"


def test_save_load_round_trip_and_atomic(tmp_path, session):
    p = CarbonProject("p", zone="PL")
    p.add_session(session("a", buckets={9: (900, 0.004, 3)},
                          apps={"x.exe": (900, 0.004, 3)}))
    p.add_activity(Activity.driving(km=10))
    path = tmp_path / "p.carbon.json"
    p.save(str(path))
    assert os.listdir(tmp_path) == ["p.carbon.json"]  # no temp file left
    q = CarbonProject.load(str(path))
    assert q.zone == "PL" and len(q.sessions) == 1 and len(q.activities) == 1
    assert q.sessions[0].seconds_by_hour == {9: 900}


def test_sessions_are_not_added_twice(session):
    p = CarbonProject("p")
    assert p.add_session(session("a"))
    assert not p.add_session(session("a"))
    assert p.add_session(session("b", start=2_000))
    assert len(p.sessions) == 2


def test_one_project_file_for_many_sessions(tmp_path, session):
    path = tmp_path / "proj.carbon.json"
    for i in range(3):
        p = CarbonProject.load(str(path)) if path.exists() else CarbonProject("p")
        p.add_session(session(f"s{i}", start=1_000 + i))
        p.save(str(path))
    assert os.listdir(tmp_path) == ["proj.carbon.json"]
    assert len(CarbonProject.load(str(path)).sessions) == 3


def test_report_opened_as_project(tmp_path, session):
    report = tmp_path / "carbon_report_x.json"
    report.write_text(json.dumps(session("r").to_dict()), encoding="utf-8")
    p = CarbonProject.load(str(report))
    assert p.loaded_from_report and len(p.sessions) == 1


def test_hpc_report_is_not_a_project(tmp_path):
    f = tmp_path / "job.carbon.json"
    f.write_text(json.dumps({"type": "hpc_job_report"}), encoding="utf-8")
    with pytest.raises(ValueError, match="HPC job report"):
        CarbonProject.load(str(f))


def test_rate_excludes_one_off_activities(session):
    p = CarbonProject("p")
    p.add_session(session(seconds=3600, grams=50))
    p.add_activity(Activity.custom("offset", co2_grams=-100_000))
    assert p.carbon_per_hour() == pytest.approx(50)
    assert p.total_carbon_grams() == pytest.approx(50 - 100_000)
    assert p.project_future(8)["projected_carbon_grams"] >= 0


def test_summary_shows_unattributed_rest(session):
    s = session(grams=50, kwh=0.08, apps={"a.exe": (3600, 0.05, 30)})
    text = s.summary()
    assert "(not attributed)" in text
    over = session(grams=10, kwh=0.01, apps={"a.exe": (3600, 0.02, 20)})
    assert "(over-attributed)" in over.summary()


def test_session_dict_round_trip(session):
    s = session(buckets={3: (60, 0.001, 0.7)}, apps={"a": (60, 0.001, 0.7)})
    s.apps["a"].seconds_by_hour = {3: 60}
    back = SessionData.from_dict(json.loads(json.dumps(s.to_dict())))
    assert back.to_dict() == s.to_dict()
