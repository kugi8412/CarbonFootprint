#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HPC / cluster carbon footprint support.

On an HPC system a workload is usually submitted through a batch scheduler
(SLURM ``sbatch``, PBS/Torque ``qsub``, LSF ``bsub``, SGE/UGE ``qsub``) and runs
on shared compute nodes where the per-laptop power tricks used elsewhere in this
package (battery discharge, foreground-window tracking) do not apply.

This module:

* detects the scheduler from its environment variables and reads the resources
  the job was *allocated* (nodes, CPU cores, GPUs, memory, wall-time limit);
* tries to obtain *measured* energy where possible - SLURM accounting
  (``sacct ... ConsumedEnergy``) when RAPL/IPMI energy gathering is enabled, or
  RAPL / ``nvidia-smi`` while a wrapped command runs;
* otherwise *estimates* energy from the allocated resources and elapsed time
  using the Green-Algorithms model (per-core + per-GPU + per-GB power, scaled by
  the data-centre PUE);
* and, crucially, always emits a transparent **manual-computation report** that
  lists how long the job ran and on exactly what hardware, with the formula and
  every assumption spelled out, so the cost can be recomputed by hand (or with
  the site's real TDP / PUE / grid figures) after the fact.

Typical use inside a batch script::

    # measure a command and write a report next to the job output
    carbon-tracker hpc run --output $SLURM_JOB_ID.carbon.json -- python train.py

or, after a job finished, from a login node::

    carbon-tracker hpc report --job-id 123456
"""

import os
import re
import time
import json
import shutil
import platform
import subprocess
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from carbon_tracker.globals import (
    _CPU_TDP_TABLE,
    _GPU_TDP_TABLE,
    _HPC_GPU_TDP_TABLE,
    SECONDS_PER_HOUR,
    WATTS_PER_KW,
    JOULES_PER_KWH,
    HPC_DEFAULT_PUE,
    HPC_DEFAULT_WATTS_PER_CORE,
    HPC_DEFAULT_GPU_WATTS,
    HPC_MEM_WATTS_PER_GB,
    HPC_DEFAULT_CPU_UTILIZATION,
    HPC_DEFAULT_GPU_UTILIZATION,
    HPC_SAMPLE_INTERVAL_SEC,
)

# Schedulers we recognise, in detection priority order: (name, sentinel env var).
_SCHEDULERS = [
    ("slurm", "SLURM_JOB_ID"),
    ("pbs", "PBS_JOBID"),
    ("lsf", "LSB_JOBID"),
    ("sge", "JOB_ID"),
]


def _match_tdp(name: str, table: list) -> float:
    """Return the first TDP in *table* whose pattern matches *name* (0 if none)."""
    if not name:
        return 0.0
    name_lower = name.lower()
    for pattern, tdp in table:
        if re.search(pattern.lower(), name_lower):
            return float(tdp)
    return 0.0


def _env_int(*names: str) -> Optional[int]:
    """First parseable positive integer among the given environment variables."""
    for name in names:
        raw = os.environ.get(name)
        if not raw:
            continue
        # Values such as "4(x2)" (SLURM_JOB_CPUS_PER_NODE) -> take the leading int.
        m = re.match(r"\s*(\d+)", raw)
        if m:
            try:
                val = int(m.group(1))
                if val > 0:
                    return val
            except ValueError:
                pass
    return None


def _count_gpus_from_env() -> int:
    """Best-effort count of GPUs visible to the job from common env variables."""
    # Explicit SLURM GPU counts.
    for name in ("SLURM_GPUS_ON_NODE", "SLURM_GPUS", "SLURM_JOB_GPUS"):
        raw = os.environ.get(name)
        if raw:
            # Forms: "2", "gpu:2", "a100:2", or a comma list of ids.
            nums = re.findall(r"(\d+)", raw)
            if ":" in raw and nums:
                return int(nums[-1])
            if "," in raw:
                return len([x for x in raw.split(",") if x.strip()])
            if nums:
                return int(nums[0])
    # Device masks set by the scheduler / CUDA / ROCm.
    for name in ("CUDA_VISIBLE_DEVICES", "GPU_DEVICE_ORDINAL", "ROCR_VISIBLE_DEVICES",
                 "HIP_VISIBLE_DEVICES", "NVIDIA_VISIBLE_DEVICES"):
        raw = os.environ.get(name)
        if raw and raw.strip().lower() not in ("", "none", "all", "void", "no-devices"):
            return len([x for x in raw.split(",") if x.strip()])
    return 0


def _slurm_mem_mb() -> Optional[int]:
    """Allocated memory in MB from SLURM env (per-node or per-cpu * cpus)."""
    raw = os.environ.get("SLURM_MEM_PER_NODE")
    nnodes = _env_int("SLURM_JOB_NUM_NODES", "SLURM_NNODES") or 1
    if raw:
        m = re.match(r"\s*(\d+)", raw)
        if m:
            return int(m.group(1)) * nnodes
    per_cpu = os.environ.get("SLURM_MEM_PER_CPU")
    if per_cpu:
        m = re.match(r"\s*(\d+)", per_cpu)
        cpus = _env_int("SLURM_CPUS_ON_NODE") or 1
        if m:
            return int(m.group(1)) * cpus * nnodes
    return None


# ============================================================
# Job model
# ============================================================
@dataclass
class HPCJobInfo:
    """Resources a batch job was allocated, read from the scheduler."""

    scheduler: str = ""
    job_id: str = ""
    job_name: str = ""
    cluster: str = ""
    partition: str = ""
    account: str = ""
    user: str = ""
    nodelist: str = ""
    num_nodes: int = 1
    num_cpus: int = 1          # total physical CPU cores allocated to the job
    num_tasks: int = 1
    cpus_per_task: int = 1
    num_gpus: int = 0
    mem_mb: Optional[int] = None
    time_limit_seconds: Optional[float] = None

    # Hardware models (best-effort; may be empty on shared/abstracted nodes).
    cpu_model: str = ""
    gpu_model: str = ""
    cpu_tdp_watts: float = 0.0          # whole-package TDP if known
    watts_per_core: float = 0.0         # derived per-core figure used for energy
    gpu_tdp_watts: float = 0.0          # per-accelerator board power

    def to_dict(self) -> dict:
        return {
            "scheduler": self.scheduler,
            "job_id": self.job_id,
            "job_name": self.job_name,
            "cluster": self.cluster,
            "partition": self.partition,
            "account": self.account,
            "user": self.user,
            "nodelist": self.nodelist,
            "num_nodes": self.num_nodes,
            "num_cpus": self.num_cpus,
            "num_tasks": self.num_tasks,
            "cpus_per_task": self.cpus_per_task,
            "num_gpus": self.num_gpus,
            "mem_mb": self.mem_mb,
            "time_limit_seconds": self.time_limit_seconds,
            "cpu_model": self.cpu_model,
            "gpu_model": self.gpu_model,
            "cpu_tdp_watts": self.cpu_tdp_watts,
            "watts_per_core": self.watts_per_core,
            "gpu_tdp_watts": self.gpu_tdp_watts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HPCJobInfo":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def detect_scheduler() -> str:
    """Return the active batch scheduler name, or "" when not inside a job."""
    for name, sentinel in _SCHEDULERS:
        if os.environ.get(sentinel):
            # JOB_ID is also used by other tools; require an SGE companion var.
            if name == "sge" and not (
                os.environ.get("SGE_TASK_ID") or os.environ.get("PE_HOSTFILE")
            ):
                continue
            return name
    return ""


def _detect_cpu_model() -> str:
    """Read the compute-node CPU model from /proc/cpuinfo (Linux) or lscpu."""
    try:
        if os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
    except OSError:
        pass
    if shutil.which("lscpu"):
        try:
            out = subprocess.check_output(
                ["lscpu"], text=True, stderr=subprocess.DEVNULL, timeout=5
            )
            for line in out.splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except (subprocess.SubprocessError, OSError):
            pass
    return ""


def _detect_gpu_model() -> str:
    """Read the first GPU model via nvidia-smi / rocm-smi when available."""
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                text=True, stderr=subprocess.DEVNULL, timeout=6,
            ).strip()
            if out:
                return out.splitlines()[0].strip()
        except (subprocess.SubprocessError, OSError):
            pass
    if shutil.which("rocm-smi"):
        try:
            out = subprocess.check_output(
                ["rocm-smi", "--showproductname"],
                text=True, stderr=subprocess.DEVNULL, timeout=6,
            )
            m = re.search(r"Card series:\s*(.+)", out)
            if m:
                return m.group(1).strip()
        except (subprocess.SubprocessError, OSError):
            pass
    return ""


def _parse_slurm_time_limit() -> Optional[float]:
    """Parse SLURM_JOB_TIME_LIMIT (minutes) or a [d-]HH:MM:SS string to seconds."""
    raw = os.environ.get("SLURM_JOB_TIME_LIMIT") or os.environ.get("SBATCH_TIMELIMIT")
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():  # SLURM exports the limit in whole minutes.
        return float(raw) * 60.0
    return _parse_elapsed(raw)


def detect_hpc_job() -> Optional[HPCJobInfo]:
    """Build an :class:`HPCJobInfo` from the current scheduler environment.

    Returns ``None`` when not running inside a recognised batch job.
    """
    scheduler = detect_scheduler()
    if not scheduler:
        return None

    job = HPCJobInfo(scheduler=scheduler)
    job.cpu_model = _detect_cpu_model()
    job.gpu_model = _detect_gpu_model()

    if scheduler == "slurm":
        job.job_id = os.environ.get("SLURM_JOB_ID", "")
        job.job_name = os.environ.get("SLURM_JOB_NAME", "")
        job.cluster = os.environ.get("SLURM_CLUSTER_NAME", "")
        job.partition = os.environ.get("SLURM_JOB_PARTITION", "")
        job.account = os.environ.get("SLURM_JOB_ACCOUNT", "")
        job.user = os.environ.get("SLURM_JOB_USER", "") or os.environ.get("USER", "")
        job.nodelist = os.environ.get("SLURM_JOB_NODELIST", "")
        job.num_nodes = _env_int("SLURM_JOB_NUM_NODES", "SLURM_NNODES") or 1
        job.num_tasks = _env_int("SLURM_NTASKS", "SLURM_NPROCS") or 1
        job.cpus_per_task = _env_int("SLURM_CPUS_PER_TASK") or 1
        cpus = _env_int("SLURM_NTASKS") and _env_int("SLURM_CPUS_PER_TASK")
        if cpus:
            job.num_cpus = job.num_tasks * job.cpus_per_task
        else:
            per_node = _env_int("SLURM_CPUS_ON_NODE", "SLURM_JOB_CPUS_PER_NODE") or 1
            job.num_cpus = per_node * job.num_nodes
        job.num_gpus = _count_gpus_from_env()
        job.mem_mb = _slurm_mem_mb()
        job.time_limit_seconds = _parse_slurm_time_limit()

    elif scheduler == "pbs":
        job.job_id = os.environ.get("PBS_JOBID", "")
        job.job_name = os.environ.get("PBS_JOBNAME", "")
        job.partition = os.environ.get("PBS_QUEUE", "")
        job.user = os.environ.get("PBS_O_LOGNAME", "") or os.environ.get("USER", "")
        job.num_nodes = _env_int("PBS_NUM_NODES") or 1
        ppn = _env_int("PBS_NUM_PPN")
        job.num_cpus = (
            _env_int("PBS_NP", "NCPUS")
            or (ppn * job.num_nodes if ppn else None)
            or _count_nodefile(os.environ.get("PBS_NODEFILE"))
            or 1
        )
        job.num_gpus = _count_gpus_from_env() or _count_nodefile(
            os.environ.get("PBS_GPUFILE")
        )

    elif scheduler == "lsf":
        job.job_id = os.environ.get("LSB_JOBID", "")
        job.job_name = os.environ.get("LSB_JOBNAME", "")
        job.partition = os.environ.get("LSB_QUEUE", "")
        job.user = os.environ.get("LSB_JOBUSER", "") or os.environ.get("USER", "")
        job.nodelist = os.environ.get("LSB_HOSTS", "")
        job.num_cpus = _env_int("LSB_DJOB_NUMPROC") or (
            len(os.environ.get("LSB_HOSTS", "").split()) or 1
        )
        hosts = os.environ.get("LSB_HOSTS", "").split()
        job.num_nodes = len(set(hosts)) or 1
        job.num_gpus = _count_gpus_from_env()

    elif scheduler == "sge":
        job.job_id = os.environ.get("JOB_ID", "")
        job.job_name = os.environ.get("JOB_NAME", "")
        job.partition = os.environ.get("QUEUE", "")
        job.user = os.environ.get("USER", "")
        job.num_cpus = _env_int("NSLOTS") or 1
        job.num_gpus = _count_gpus_from_env()
        job.num_nodes = 1

    _resolve_job_power(job)
    return job


def _count_nodefile(path: Optional[str]) -> int:
    """Count non-empty lines in a scheduler node/gpu file (0 if unavailable)."""
    if not path or not os.path.exists(path):
        return 0
    try:
        with open(path) as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def _resolve_job_power(job: HPCJobInfo) -> None:
    """Fill in per-core and per-GPU power figures from the detected models."""
    # CPU: prefer a model-specific package TDP divided across the node's cores.
    pkg_tdp = _match_tdp(job.cpu_model, _CPU_TDP_TABLE)
    job.cpu_tdp_watts = pkg_tdp
    cores_for_tdp = _env_int("SLURM_CPUS_ON_NODE") or job.num_cpus or 1
    if pkg_tdp > 0 and cores_for_tdp > 0:
        job.watts_per_core = pkg_tdp / cores_for_tdp
    if job.watts_per_core <= 0:
        job.watts_per_core = HPC_DEFAULT_WATTS_PER_CORE

    # GPU: data-centre table first, then the consumer table, then a default.
    if job.num_gpus > 0:
        gpu_tdp = _match_tdp(job.gpu_model, _HPC_GPU_TDP_TABLE)
        if gpu_tdp <= 0:
            gpu_tdp = _match_tdp(job.gpu_model, _GPU_TDP_TABLE)
        job.gpu_tdp_watts = gpu_tdp if gpu_tdp > 0 else HPC_DEFAULT_GPU_WATTS


# ============================================================
# sacct (SLURM accounting) lookup
# ============================================================
def _parse_elapsed(text: str) -> Optional[float]:
    """Parse a SLURM/PBS duration ``[DD-]HH:MM:SS[.ms]`` into seconds."""
    text = (text or "").strip()
    if not text:
        return None
    days = 0
    if "-" in text:
        d, text = text.split("-", 1)
        try:
            days = int(d)
        except ValueError:
            days = 0
    parts = text.split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        return None
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0.0, parts[0], parts[1]
    elif len(parts) == 1:
        h, m, s = 0.0, 0.0, parts[0]
    else:
        return None
    return days * 86400 + h * 3600 + m * 60 + s


def _parse_energy_to_kwh(text: str) -> Optional[float]:
    """Parse a SLURM ConsumedEnergy value to kWh.

    ``ConsumedEnergyRaw`` is plain joules; ``ConsumedEnergy`` is a human string
    such as ``1.23M`` (mega-joules) or ``500K``. Returns ``None`` for 0/empty.
    """
    text = (text or "").strip()
    if not text or text in ("0", "0.00", "0K"):
        return None
    m = re.match(r"([\d.]+)\s*([kKmMgG]?)", text)
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    mult = {"": 1.0, "k": 1e3, "m": 1e6, "g": 1e9}[m.group(2).lower()]
    joules = value * mult
    if joules <= 0:
        return None
    return joules / JOULES_PER_KWH


def query_slurm_accounting(job_id: str) -> dict:
    """Query ``sacct`` for a finished/running job's elapsed time and energy.

    Returns a dict that may contain ``elapsed_seconds``, ``energy_kwh``
    (measured, when RAPL/IPMI energy accounting is enabled site-wide) and
    ``total_cpu_seconds``. Empty dict when ``sacct`` is unavailable or silent.
    """
    if not job_id or not shutil.which("sacct"):
        return {}
    try:
        out = subprocess.check_output(
            [
                "sacct", "-j", str(job_id), "--noheader", "--parsable2",
                "--format=JobID,ElapsedRaw,TotalCPU,ConsumedEnergyRaw,ConsumedEnergy",
            ],
            text=True, stderr=subprocess.DEVNULL, timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        return {}

    result: dict = {}
    energy_kwh = 0.0
    for line in out.strip().splitlines():
        cols = line.split("|")
        if len(cols) < 5:
            continue
        jid, elapsed_raw, total_cpu, energy_raw, energy_str = cols[:5]
        # The top-level job row (no ".step" suffix) carries the wall time.
        if "." not in jid:
            try:
                if elapsed_raw.strip():
                    result["elapsed_seconds"] = float(elapsed_raw)
            except ValueError:
                pass
            cpu_secs = _parse_elapsed(total_cpu)
            if cpu_secs:
                result["total_cpu_seconds"] = cpu_secs
        # Energy is reported per step; accumulate the maximum sensible value.
        e = None
        try:
            if energy_raw.strip() and float(energy_raw) > 0:
                e = float(energy_raw) / JOULES_PER_KWH
        except ValueError:
            e = None
        if e is None:
            e = _parse_energy_to_kwh(energy_str)
        if e:
            energy_kwh = max(energy_kwh, e)
    if energy_kwh > 0:
        result["energy_kwh"] = energy_kwh
    return result


# ============================================================
# Report
# ============================================================
@dataclass
class HPCReport:
    """Carbon footprint of one HPC job, measured or estimated, plus a
    transparent by-hand worksheet."""

    job: Optional[HPCJobInfo] = None
    elapsed_seconds: float = 0.0
    pue: float = HPC_DEFAULT_PUE
    cpu_utilization: float = HPC_DEFAULT_CPU_UTILIZATION
    gpu_utilization: float = HPC_DEFAULT_GPU_UTILIZATION

    energy_kwh: float = 0.0
    carbon_grams: float = 0.0
    zone: str = ""
    intensity: float = 0.0
    intensity_real: bool = False

    energy_measured: bool = False
    energy_source: str = "estimate"      # estimate | slurm-sacct | rapl+nvidia-smi
    # Power breakdown (watts) used for the estimate; 0 when energy was measured.
    cpu_watts: float = 0.0
    gpu_watts: float = 0.0
    mem_watts: float = 0.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "type": "hpc_job_report",
            "generated_at": time.time(),
            "job": self.job.to_dict() if self.job else None,
            "elapsed_seconds": self.elapsed_seconds,
            "elapsed_hours": self.elapsed_seconds / SECONDS_PER_HOUR,
            "pue": self.pue,
            "cpu_utilization": self.cpu_utilization,
            "gpu_utilization": self.gpu_utilization,
            "energy_kwh": self.energy_kwh,
            "carbon_grams": self.carbon_grams,
            "zone": self.zone,
            "intensity_gco2_per_kwh": self.intensity,
            "intensity_real": self.intensity_real,
            "energy_measured": self.energy_measured,
            "energy_source": self.energy_source,
            "power_breakdown_watts": {
                "cpu": self.cpu_watts,
                "gpu": self.gpu_watts,
                "memory": self.mem_watts,
                "total_it": self.cpu_watts + self.gpu_watts + self.mem_watts,
            },
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HPCReport":
        job = HPCJobInfo.from_dict(d["job"]) if d.get("job") else None
        pb = d.get("power_breakdown_watts", {})
        return cls(
            job=job,
            elapsed_seconds=d.get("elapsed_seconds", 0.0),
            pue=d.get("pue", HPC_DEFAULT_PUE),
            cpu_utilization=d.get("cpu_utilization", HPC_DEFAULT_CPU_UTILIZATION),
            gpu_utilization=d.get("gpu_utilization", HPC_DEFAULT_GPU_UTILIZATION),
            energy_kwh=d.get("energy_kwh", 0.0),
            carbon_grams=d.get("carbon_grams", 0.0),
            zone=d.get("zone", ""),
            intensity=d.get("intensity_gco2_per_kwh", 0.0),
            intensity_real=d.get("intensity_real", False),
            energy_measured=d.get("energy_measured", False),
            energy_source=d.get("energy_source", "estimate"),
            cpu_watts=pb.get("cpu", 0.0),
            gpu_watts=pb.get("gpu", 0.0),
            mem_watts=pb.get("memory", 0.0),
            notes=d.get("notes", []),
        )

    def save(self, filepath: str) -> None:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    # -- human-readable output -------------------------------------------------
    def summary(self) -> str:
        job = self.job or HPCJobInfo()
        hours = self.elapsed_seconds / SECONDS_PER_HOUR
        lines = [
            "<== HPC Carbon Footprint ==>",
            f"  Scheduler:   {job.scheduler or 'n/a'}"
            + (f"  (job {job.job_id})" if job.job_id else ""),
        ]
        if job.job_name:
            lines.append(f"  Job name:    {job.job_name}")
        if job.partition or job.cluster:
            lines.append(
                f"  Cluster:     {job.cluster or '?'} / {job.partition or '?'}"
            )
        lines.append(
            f"  Resources:   {job.num_nodes} node(s), {job.num_cpus} CPU core(s), "
            f"{job.num_gpus} GPU(s)"
            + (f", {job.mem_mb} MB RAM" if job.mem_mb else "")
        )
        if job.cpu_model:
            lines.append(f"  CPU model:   {job.cpu_model}")
        if job.num_gpus and job.gpu_model:
            lines.append(f"  GPU model:   {job.gpu_model}")
        lines.append(f"  Wall time:   {_fmt_hms(self.elapsed_seconds)}  ({hours:.3f} h)")
        tag = "MEASURED" if self.energy_measured else "ESTIMATED"
        lines.append(f"  Energy:      {self.energy_kwh * 1000:.2f} Wh   [{tag}: {self.energy_source}]")
        lines.append(
            f"  CO2:         {self.carbon_grams:.2f} g"
            + (f"  ({self.carbon_grams / 1000:.4f} kg)" if self.carbon_grams >= 1000 else "")
        )
        lines.append(
            f"  Grid:        {self.zone or '?'} @ {self.intensity:.0f} gCO2/kWh"
            f"{'*' if self.intensity_real else ' (estimate)'}"
        )
        if not self.energy_measured:
            lines.append(f"  PUE:         {self.pue}")
        for note in self.notes:
            lines.append(f"  ! {note}")
        return "\n".join(lines)

    def manual_computation_report(self) -> str:
        """A transparent worksheet so the cost can be recomputed by hand.

        Always produced - especially valuable when energy could not be measured
        on the node, since it records exactly *how long* the job ran and *on
        what* hardware, plus the formula and every assumption.
        """
        job = self.job or HPCJobInfo()
        hours = self.elapsed_seconds / SECONDS_PER_HOUR
        L: List[str] = []
        L.append("=" * 70)
        L.append("HPC CARBON FOOTPRINT - MANUAL COMPUTATION WORKSHEET")
        L.append("=" * 70)
        L.append("")
        L.append("This worksheet lets you recompute (or audit) the carbon cost by")
        L.append("hand using your site's real numbers. Substitute any value you")
        L.append("know more precisely (per-core TDP, PUE, grid intensity).")
        L.append("")
        L.append("-- 1. What ran, for how long --------------------------------------")
        L.append(f"   Scheduler / job  : {job.scheduler or 'n/a'} {job.job_id}".rstrip())
        if job.job_name:
            L.append(f"   Job name         : {job.job_name}")
        if job.cluster or job.partition:
            L.append(f"   Cluster / queue  : {job.cluster or '?'} / {job.partition or '?'}")
        if job.nodelist:
            L.append(f"   Node list        : {job.nodelist}")
        L.append(f"   Wall-clock time  : {_fmt_hms(self.elapsed_seconds)}  = {hours:.4f} h")
        L.append("")
        L.append("-- 2. Allocated hardware ------------------------------------------")
        L.append(f"   Nodes            : {job.num_nodes}")
        L.append(f"   CPU cores (total): {job.num_cpus}")
        L.append(f"   CPU model        : {job.cpu_model or '(unknown - fill in)'}")
        if job.cpu_tdp_watts > 0:
            L.append(f"   CPU package TDP  : {job.cpu_tdp_watts:.0f} W (table lookup)")
        L.append(f"   -> per-core power: {job.watts_per_core:.2f} W/core "
                 f"{'(from TDP)' if job.cpu_tdp_watts > 0 else '(default assumption)'}")
        L.append(f"   GPUs             : {job.num_gpus}")
        if job.num_gpus:
            L.append(f"   GPU model        : {job.gpu_model or '(unknown - fill in)'}")
            L.append(f"   -> per-GPU power : {job.gpu_tdp_watts:.0f} W")
        mem_gb = (job.mem_mb or 0) / 1024.0
        L.append(f"   Memory           : {mem_gb:.1f} GB"
                 f" ({job.mem_mb} MB)" if job.mem_mb else "   Memory           : (unspecified)")
        L.append("")
        L.append("-- 3. Assumptions -------------------------------------------------")
        L.append(f"   CPU utilisation  : {self.cpu_utilization * 100:.0f} %")
        if job.num_gpus:
            L.append(f"   GPU utilisation  : {self.gpu_utilization * 100:.0f} %")
        L.append(f"   Memory power     : {HPC_MEM_WATTS_PER_GB} W/GB")
        L.append(f"   PUE (datacentre) : {self.pue}")
        L.append(f"   Grid intensity   : {self.intensity:.0f} gCO2/kWh"
                 f" [{self.zone or '?'}]"
                 + (" (live)" if self.intensity_real
                    else " (estimate - set --zone)" if not self.zone
                    else " (estimate)"))
        L.append("")
        L.append("-- 4. Formula -----------------------------------------------------")
        L.append("   IT_power(W) = cores * Wpc * Ucpu")
        L.append("               + gpus  * Wpg * Ugpu")
        L.append("               + mem_GB * Wmem")
        L.append("   Energy(kWh) = IT_power * hours * PUE / 1000")
        L.append("   CO2(g)      = Energy(kWh) * grid_intensity(gCO2/kWh)")
        L.append("")
        L.append("-- 5. Worked numbers ----------------------------------------------")
        cpu_w = self.cpu_watts
        gpu_w = self.gpu_watts
        mem_w = self.mem_watts
        it_w = cpu_w + gpu_w + mem_w
        L.append(f"   CPU power  = {job.num_cpus} * {job.watts_per_core:.2f} "
                 f"* {self.cpu_utilization:.2f} = {cpu_w:.1f} W")
        if job.num_gpus:
            L.append(f"   GPU power  = {job.num_gpus} * {job.gpu_tdp_watts:.0f} "
                     f"* {self.gpu_utilization:.2f} = {gpu_w:.1f} W")
        if mem_w > 0:
            L.append(f"   Mem power  = {mem_gb:.1f} * {HPC_MEM_WATTS_PER_GB} = {mem_w:.1f} W")
        L.append(f"   IT power   = {it_w:.1f} W")
        if self.energy_measured:
            L.append(f"   (Energy was MEASURED directly: {self.energy_kwh * 1000:.2f} Wh "
                     f"via {self.energy_source}; the figures above are reference only.)")
        else:
            L.append(f"   Energy     = {it_w:.1f} W * {hours:.4f} h * {self.pue} / 1000 "
                     f"= {self.energy_kwh:.6f} kWh = {self.energy_kwh * 1000:.2f} Wh")
        L.append(f"   CO2        = {self.energy_kwh:.6f} kWh * {self.intensity:.0f} "
                 f"= {self.carbon_grams:.2f} g")
        L.append("")
        L.append("-- Result ---------------------------------------------------------")
        L.append(f"   ENERGY : {self.energy_kwh * 1000:.2f} Wh   "
                 f"({'measured' if self.energy_measured else 'estimated'})")
        L.append(f"   CO2    : {self.carbon_grams:.2f} g")
        if self.notes:
            L.append("")
            L.append("-- Notes ----------------------------------------------------------")
            for note in self.notes:
                L.append(f"   * {note}")
        L.append("=" * 70)
        return "\n".join(L)


def _fmt_hms(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s"


# ============================================================
# Estimation + orchestration
# ============================================================
def estimate_energy_kwh(
    job: HPCJobInfo,
    elapsed_seconds: float,
    pue: float = HPC_DEFAULT_PUE,
    cpu_utilization: float = HPC_DEFAULT_CPU_UTILIZATION,
    gpu_utilization: float = HPC_DEFAULT_GPU_UTILIZATION,
) -> Tuple[float, float, float, float]:
    """Green-Algorithms energy estimate.

    Returns ``(energy_kwh, cpu_watts, gpu_watts, mem_watts)``.
    """
    hours = elapsed_seconds / SECONDS_PER_HOUR
    cpu_watts = job.num_cpus * job.watts_per_core * cpu_utilization
    gpu_watts = job.num_gpus * job.gpu_tdp_watts * gpu_utilization
    mem_gb = (job.mem_mb or 0) / 1024.0
    mem_watts = mem_gb * HPC_MEM_WATTS_PER_GB
    it_watts = cpu_watts + gpu_watts + mem_watts
    energy_kwh = (it_watts * hours * pue) / WATTS_PER_KW
    return energy_kwh, cpu_watts, gpu_watts, mem_watts


def build_hpc_report(
    job: Optional[HPCJobInfo] = None,
    elapsed_seconds: Optional[float] = None,
    zone: Optional[str] = None,
    api_key: str = "",
    pue: float = HPC_DEFAULT_PUE,
    cpu_utilization: float = HPC_DEFAULT_CPU_UTILIZATION,
    gpu_utilization: float = HPC_DEFAULT_GPU_UTILIZATION,
    measured_energy_kwh: Optional[float] = None,
    measured_source: str = "",
    use_sacct: bool = True,
) -> HPCReport:
    """Assemble a complete :class:`HPCReport`.

    Energy precedence: caller-supplied ``measured_energy_kwh`` (e.g. sampled
    while wrapping a command) -> SLURM ``sacct`` ConsumedEnergy -> estimate.
    The grid intensity is looked up for *zone* (auto-detected when omitted).
    """
    # Lazy imports keep `requests` optional for pure-estimation use.
    from carbon_tracker.carbon_api import (
        auto_detect_zone,
        fetch_carbon_intensity,
        get_fallback_intensity,
    )

    if job is None:
        job = detect_hpc_job() or HPCJobInfo()
    _resolve_job_power(job)

    report = HPCReport(
        job=job, pue=pue,
        cpu_utilization=cpu_utilization, gpu_utilization=gpu_utilization,
    )

    # --- elapsed time + (optionally) measured energy from accounting ----------
    sacct: dict = {}
    if use_sacct and job.scheduler == "slurm" and job.job_id:
        sacct = query_slurm_accounting(job.job_id)

    if elapsed_seconds is not None:
        report.elapsed_seconds = float(elapsed_seconds)
    elif sacct.get("elapsed_seconds"):
        report.elapsed_seconds = float(sacct["elapsed_seconds"])
    elif job.time_limit_seconds:
        report.elapsed_seconds = float(job.time_limit_seconds)
        report.notes.append(
            "Elapsed time unknown; used the job's TIME LIMIT as an upper bound. "
            "Pass --elapsed or run via `hpc run` for the real wall time."
        )

    # --- grid intensity -------------------------------------------------------
    if not zone:
        detected, _ = auto_detect_zone()
        zone = detected or ""
    report.zone = zone
    if zone:
        intensity, is_real = fetch_carbon_intensity(zone, api_key)
    else:
        intensity, is_real = get_fallback_intensity("PL"), False
        report.notes.append(
            "Grid zone could not be detected; used a generic fallback intensity. "
            "Pass --zone (e.g. --zone DE) for an accurate figure."
        )
    report.intensity = intensity
    report.intensity_real = is_real

    # --- energy: measured > sacct > estimate ----------------------------------
    energy_est, cpu_w, gpu_w, mem_w = estimate_energy_kwh(
        job, report.elapsed_seconds, pue, cpu_utilization, gpu_utilization
    )
    report.cpu_watts, report.gpu_watts, report.mem_watts = cpu_w, gpu_w, mem_w

    if measured_energy_kwh and measured_energy_kwh > 0:
        report.energy_kwh = measured_energy_kwh
        report.energy_measured = True
        report.energy_source = measured_source or "measured"
    elif sacct.get("energy_kwh"):
        report.energy_kwh = sacct["energy_kwh"]
        report.energy_measured = True
        report.energy_source = "slurm-sacct"
    else:
        report.energy_kwh = energy_est
        report.energy_measured = False
        report.energy_source = "estimate"
        if report.elapsed_seconds <= 0:
            report.notes.append(
                "No elapsed time available - energy/CO2 are 0. Provide --elapsed "
                "seconds or measure the run with `hpc run`."
            )
        else:
            report.notes.append(
                "Energy is ESTIMATED from allocated resources (no node power "
                "sensor / SLURM energy accounting was available). See the manual "
                "worksheet to refine with real per-core TDP and PUE."
            )

    report.carbon_grams = report.energy_kwh * report.intensity
    return report


# ============================================================
# `hpc run`: wrap a command, measure wall time + power while it runs
# ============================================================
def _sample_power_once(has_nvidia: bool) -> Optional[float]:
    """Instantaneous IT power (W) from RAPL + nvidia-smi, or None if neither."""
    from carbon_tracker.power import read_cpu_power_watts, read_gpu_power_draw

    total = 0.0
    got = False
    cpu_w, _src = read_cpu_power_watts()
    if cpu_w and cpu_w > 0:
        total += cpu_w
        got = True
    if has_nvidia:
        gpu_w = read_gpu_power_draw()
        if gpu_w and gpu_w > 0:
            total += gpu_w
            got = True
    return total if got else None


def run_and_measure(
    command: List[str],
    sample_interval: float = HPC_SAMPLE_INTERVAL_SEC,
) -> Tuple[int, float, Optional[float], str]:
    """Run *command*, integrating measured power over its lifetime.

    Returns ``(exit_code, elapsed_seconds, measured_energy_kwh_or_None,
    source)``. ``measured_energy_kwh`` is ``None`` when no node power sensor was
    readable (the report then falls back to estimation).
    """
    import threading

    has_nvidia = shutil.which("nvidia-smi") is not None
    energy_j = 0.0
    samples = 0
    stop = threading.Event()

    def _sampler():
        nonlocal energy_j, samples
        last = time.time()
        while not stop.is_set():
            watts = _sample_power_once(has_nvidia)
            now = time.time()
            if watts is not None:
                energy_j += watts * (now - last)
                samples += 1
            last = now
            stop.wait(sample_interval)

    sampler = threading.Thread(target=_sampler, daemon=True)
    start = time.time()
    sampler.start()
    try:
        proc = subprocess.Popen(command)
        exit_code = proc.wait()
    finally:
        stop.set()
        sampler.join(timeout=sample_interval + 2)
    elapsed = time.time() - start

    if samples > 0 and energy_j > 0:
        return exit_code, elapsed, energy_j / JOULES_PER_KWH, "rapl+nvidia-smi"
    return exit_code, elapsed, None, ""
