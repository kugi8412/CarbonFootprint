#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hardware auto-detection for Carbon Footprint Tracker.
"""

import re
import os
import platform
import subprocess

from carbon_tracker.models import HardwareInfo
from carbon_tracker.globals import _CPU_TDP_TABLE, _GPU_TDP_TABLE


def _match_tdp(name: str, table: list) -> float:
    name_lower = name.lower()

    for pattern, tdp in table:
        if re.search(pattern.lower(), name_lower):
            return tdp

    return 0.0


def detect_cpu_name() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            return name.strip()

        elif system == "Linux":
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":")[1].strip()
        elif system == "Darwin":
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                text=True,
            )
            return out.strip()

    except Exception:
        pass
    return ""


def detect_cpu_cores() -> int:
    try:
        import psutil

        return psutil.cpu_count(logical=False) or os.cpu_count() or 4
    except ImportError:
        return os.cpu_count() or 4


def _is_wsl() -> bool:
    """True when running under Windows Subsystem for Linux."""
    if platform.system() != "Linux":
        return False
    try:
        with open("/proc/version") as f:
            version_str = f.read().lower()
        return "microsoft" in version_str or "wsl" in version_str
    except OSError:
        return False


def detect_cpu_tdp_from_device() -> float:
    """Read the real CPU package power limit (PL1 ~= TDP) from the Intel/AMD
    RAPL powercap interface. Returns watts, or 0.0 when unavailable
    (Windows, macOS and most WSL setups, where powercap is not exposed)."""
    if platform.system() != "Linux":
        return 0.0

    base = "/sys/class/powercap"
    if not os.path.isdir(base):
        return 0.0

    try:
        for entry in sorted(os.listdir(base)):
            # Top-level package domains look like "intel-rapl:0",
            # not subzones such as "intel-rapl:0:0".
            if not re.match(r"intel-rapl:\d+$", entry):
                continue

            domain = os.path.join(base, entry)

            # Confirm this domain is a CPU package (skip "psys", "dram").
            name_file = os.path.join(domain, "name")
            if os.path.exists(name_file):
                with open(name_file) as f:
                    if not f.read().strip().startswith("package"):
                        continue

            # Prefer the sustained long-term limit, then the max power rating.
            for fname in ("constraint_0_power_limit_uw", "constraint_0_max_power_uw"):
                fpath = os.path.join(domain, fname)
                if os.path.exists(fpath):
                    with open(fpath) as f:
                        micro_watts = int(f.read().strip())
                    if micro_watts > 0:
                        return micro_watts / 1_000_000.0
    except (OSError, ValueError):
        pass
    return 0.0


def detect_gpu_tdp_from_device() -> float:
    """Query the real GPU board power limit from the driver. nvidia-smi works on
    Windows, Linux and WSL2; rocm-smi covers AMD on Linux. Returns watts, or
    0.0 when no supported GPU/driver is present."""
    # NVIDIA: the default power limit equals the board TDP.
    for query in ("power.default_limit", "power.max_limit"):
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    f"--query-gpu={query}",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            if out:
                watts = float(out.splitlines()[0].strip())
                if watts > 0:
                    return watts
        except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
            pass

    # AMD ROCm (Linux).
    try:
        out = subprocess.check_output(
            ["rocm-smi", "--showmaxpower"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        match = re.search(r"([\d.]+)\s*W", out)
        if match:
            watts = float(match.group(1))
            if watts > 0:
                return watts
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        pass
    return 0.0


def detect_gpu_name() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            import winreg

            for i in range(10):
                try:
                    subkey = (
                        r"SYSTEM\CurrentControlSet\Control\Class"
                        r"\{4d36e968-e325-11ce-bfc1-08002be10318}"
                        f"\\{i:04d}"
                    )
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey)
                    desc, _ = winreg.QueryValueEx(key, "DriverDesc")
                    winreg.CloseKey(key)
                    if (
                        desc
                        and "intel" not in desc.lower()
                        and "uhd" not in desc.lower()
                    ):
                        return desc
                    if desc and not detect_gpu_name.__dict__.get("_fallback"):
                        detect_gpu_name._fallback = desc
                except OSError:
                    continue
            return getattr(detect_gpu_name, "_fallback", "")
        elif system == "Linux":
            # Try nvidia-smi first for NVIDIA GPUs
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if out:
                    return out.splitlines()[0].strip()
            except (FileNotFoundError, subprocess.CalledProcessError):
                pass

            # Fallback to lspci
            out = subprocess.check_output(
                ["lspci"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                if any(x in line.lower() for x in ["vga", "3d", "display"]):
                    parts = line.split(":")
                    if len(parts) >= 3:
                        return parts[-1].strip()
        elif system == "Darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPDisplaysDataType"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                if "chipset model" in line.lower():
                    return line.split(":")[-1].strip()
    except Exception:
        pass
    return ""


def detect_is_laptop() -> bool:
    system = platform.system()
    try:
        if system == "Windows":
            import ctypes

            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [
                    ("ACLineStatus", ctypes.c_byte),
                    ("BatteryFlag", ctypes.c_byte),
                    ("BatteryLifePercent", ctypes.c_byte),
                    ("SystemStatusFlag", ctypes.c_byte),
                    ("BatteryLifeTime", ctypes.c_ulong),
                    ("BatteryFullLifeTime", ctypes.c_ulong),
                ]

            status = SYSTEM_POWER_STATUS()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
            return status.BatteryFlag not in (128, 255)
        elif system == "Linux":
            # Detect WSL - WSL does not have real battery info
            is_wsl = _is_wsl()

            if is_wsl:
                # On WSL, fall back to DMI chassis type from the host
                try:
                    chassis_path = "/sys/class/dmi/id/chassis_type"
                    if os.path.exists(chassis_path):
                        with open(chassis_path) as f:
                            chassis_type = int(f.read().strip())
                        # 9=Laptop, 10=Notebook, 14=Sub-Notebook, 31=Convertible, 32=Detachable
                        if chassis_type in (9, 10, 14, 31, 32):
                            return True
                        return False
                except (OSError, ValueError):
                    pass
                return False  # default to desktop on WSL if no info

            # Native Linux: check multiple battery paths
            power_supply_dir = "/sys/class/power_supply"
            if os.path.isdir(power_supply_dir):
                for entry in os.listdir(power_supply_dir):
                    type_file = os.path.join(power_supply_dir, entry, "type")
                    if os.path.exists(type_file):
                        with open(type_file) as f:
                            if f.read().strip() == "Battery":
                                return True

            # Fallback: check chassis type
            try:
                chassis_path = "/sys/class/dmi/id/chassis_type"
                if os.path.exists(chassis_path):
                    with open(chassis_path) as f:
                        chassis_type = int(f.read().strip())
                    if chassis_type in (9, 10, 14, 31, 32):
                        return True
            except (OSError, ValueError):
                pass

            return False
        elif system == "Darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPHardwareDataType"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            return "macbook" in out.lower()
    except Exception:
        pass
    return True  # default to laptop (safer TDP estimate)


def detect_hardware() -> HardwareInfo:
    """Auto-detect all hardware specs."""
    info = HardwareInfo()
    info.cpu_name = detect_cpu_name()
    info.cpu_cores = detect_cpu_cores()
    info.gpu_name = detect_gpu_name()
    info.is_laptop = detect_is_laptop()

    # CPU TDP: prefer the real value read from the device (RAPL), then the
    # lookup table, then a core-count heuristic.
    cpu_tdp = detect_cpu_tdp_from_device()
    if cpu_tdp <= 0:
        cpu_tdp = _match_tdp(info.cpu_name, _CPU_TDP_TABLE)
    if cpu_tdp > 0:
        info.cpu_tdp_watts = cpu_tdp
    else:
        # Heuristic
        if info.cpu_cores <= 4:
            info.cpu_tdp_watts = 35.0
        elif info.cpu_cores <= 8:
            info.cpu_tdp_watts = 65.0
        else:
            info.cpu_tdp_watts = 105.0

    # GPU TDP: prefer the real board power limit from the driver, then the table.
    gpu_tdp = detect_gpu_tdp_from_device()
    if gpu_tdp <= 0:
        gpu_tdp = _match_tdp(info.gpu_name, _GPU_TDP_TABLE)

    if gpu_tdp > 0:
        info.gpu_tdp_watts = gpu_tdp
        if not info.gpu_name:
            info.gpu_name = "GPU (driver-reported)"
    else:
        info.gpu_tdp_watts = 15.0

    info.base_system_watts = 15.0 if info.is_laptop else 40.0
    info.auto_detected = bool(info.cpu_name or info.gpu_name)
    return info
