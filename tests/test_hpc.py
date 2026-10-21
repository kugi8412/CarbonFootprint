import json
import sys

import pytest

from carbon_tracker import hpc
from carbon_tracker.hpc import HPCJobInfo, build_hpc_report

XEON = "Intel(R) Xeon(R) CPU E5-2697 v3 @ 2.60GHz"


def test_per_core_power_uses_socket_cores():
    job = HPCJobInfo(num_cpus=4, cpu_model=XEON)
    hpc._resolve_job_power(job)
    assert job.cpu_tdp_watts == 145
    assert job.watts_per_core == pytest.approx(145 / 14)


def test_per_core_power_from_detected_socket(monkeypatch):
    monkeypatch.setattr(hpc, "_detect_cores_per_socket", lambda: 16)
    job = HPCJobInfo(num_cpus=4, cpu_model="Intel(R) Xeon(R) Gold 9999")
    hpc._resolve_job_power(job)
    assert job.watts_per_core == pytest.approx(105 / 16)


def test_per_core_power_default(monkeypatch):
    monkeypatch.setattr(hpc, "_detect_cores_per_socket", lambda: 0)
    job = HPCJobInfo(num_cpus=4, cpu_model="")
    hpc._resolve_job_power(job)
    assert job.watts_per_core == 9.0


def test_estimate_math():
    job = HPCJobInfo(scheduler="slurm", num_cpus=4, mem_mb=8192, cpu_model=XEON)
    rep = build_hpc_report(job=job, elapsed_seconds=3600, zone="PL", use_sacct=False)
    it_watts = 4 * 145 / 14 + 8 * 0.3725
    assert rep.energy_kwh == pytest.approx(it_watts * 1.5 / 1000)
    assert rep.carbon_grams == pytest.approx(rep.energy_kwh * rep.intensity)
    assert not rep.energy_measured
    assert "MANUAL COMPUTATION" in rep.manual_computation_report()


@pytest.mark.parametrize("kwargs", [
    {"cpu_utilization": 1.1429}, {"cpu_utilization": 0.0},
    {"gpu_utilization": -1.0}, {"pue": 0.9},
])
def test_invalid_assumptions_are_rejected(kwargs):
    with pytest.raises(ValueError):
        build_hpc_report(job=HPCJobInfo(num_cpus=4), elapsed_seconds=10, zone="PL",
                         use_sacct=False, **kwargs)


def test_measured_energy_wins():
    rep = build_hpc_report(job=HPCJobInfo(num_cpus=4), elapsed_seconds=10, zone="FR",
                           measured_energy_kwh=0.5, measured_source="rapl+nvidia-smi",
                           use_sacct=False)
    assert rep.energy_measured and rep.energy_kwh == 0.5


def test_report_round_trip(tmp_path):
    rep = build_hpc_report(job=HPCJobInfo(num_cpus=2), elapsed_seconds=60, zone="DE",
                           use_sacct=False)
    path = tmp_path / "job.carbon.json"
    rep.save(str(path))
    back = hpc.HPCReport.from_dict(json.loads(path.read_text()))
    assert back.energy_kwh == pytest.approx(rep.energy_kwh)


@pytest.mark.parametrize("text,seconds", [
    ("1-02:03:04", 93784), ("05:06", 306), ("42", 42), ("", None),
])
def test_parse_elapsed(text, seconds):
    assert hpc._parse_elapsed(text) == seconds


def test_parse_energy():
    assert hpc._parse_energy_to_kwh("3.6M") == pytest.approx(1.0)
    assert hpc._parse_energy_to_kwh("0") is None


def test_detect_slurm_job(monkeypatch):
    for var in ("CUDA_VISIBLE_DEVICES", "SLURM_GPUS", "SLURM_JOB_GPUS", "PBS_JOBID",
                "LSB_JOBID", "SLURM_CPUS_ON_NODE", "SLURM_MEM_PER_CPU"):
        monkeypatch.delenv(var, raising=False)
    env = {"SLURM_JOB_ID": "123", "SLURM_JOB_NAME": "salmon", "SLURM_NTASKS": "2",
           "SLURM_CPUS_PER_TASK": "4", "SLURM_JOB_NUM_NODES": "1",
           "SLURM_MEM_PER_NODE": "8000", "SLURM_GPUS_ON_NODE": "2"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    job = hpc.detect_hpc_job()
    assert job.scheduler == "slurm" and job.job_id == "123"
    assert (job.num_cpus, job.num_gpus, job.mem_mb) == (8, 2, 8000)


def test_not_in_a_job(monkeypatch):
    for var in ("SLURM_JOB_ID", "PBS_JOBID", "LSB_JOBID", "JOB_ID"):
        monkeypatch.delenv(var, raising=False)
    assert hpc.detect_hpc_job() is None


def test_measured_source_names_only_real_sensors(monkeypatch):
    from carbon_tracker import power

    monkeypatch.setattr(hpc.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(power, "read_cpu_power_watts", lambda: (None, None))
    monkeypatch.setattr(power, "read_gpu_power_draw", lambda: 100.0)
    code, elapsed, energy, source = hpc.run_and_measure(
        [sys.executable, "-c", "import time; time.sleep(1.0)"], sample_interval=0.4)
    assert code == 0 and source == "nvidia-smi"
    assert energy * 3_600_000 == pytest.approx(100.0 * elapsed, rel=0.15)

    rep = build_hpc_report(job=HPCJobInfo(num_cpus=2), elapsed_seconds=elapsed, zone="PL",
                           measured_energy_kwh=energy, measured_source=source,
                           use_sacct=False)
    assert rep.energy_measured
    assert any("CPU energy is NOT included" in n for n in rep.notes)
    assert any("other users" in n for n in rep.notes)


def test_run_and_measure_wraps_a_command():
    code, elapsed, energy, source = hpc.run_and_measure(
        [sys.executable, "-c", "import sys; sys.exit(3)"], sample_interval=0.1)
    assert code == 3 and elapsed > 0
    assert energy is None or energy > 0
