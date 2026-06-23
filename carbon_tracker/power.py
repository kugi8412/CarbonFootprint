#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Real system power measurement from the battery.

When a laptop runs on battery, the battery's discharge rate is the *actual*
whole-system power draw in watts (CPU + GPU + screen + everything). Reading it
gives a precise, measured figure that replaces TDP-based heuristics.

``read_system_power_watts()`` returns ``(watts, source)`` where ``watts`` is the
instantaneous discharge power and ``source`` describes how it was obtained, or
``(None, None)`` when no measurement is available (e.g. on AC power, desktops,
or when the platform does not expose battery telemetry).
"""

import os
import platform
import subprocess
import time
from typing import Optional, Tuple


def _is_wsl() -> bool:
    if platform.system() != "Linux":
        return False
    try:
        with open("/proc/version") as f:
            v = f.read().lower()
        return "microsoft" in v or "wsl" in v
    except OSError:
        return False


def _run_first_float(cmd: list) -> Optional[float]:
    """Run a command and parse the first numeric token of its output."""
    try:
        out = subprocess.check_output(
            cmd, text=True, stderr=subprocess.DEVNULL, timeout=6
        ).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError, OSError):
        return None
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            return float(line.split(",")[0].split()[0])
        except (ValueError, IndexError):
            continue
    return None


def read_battery_status() -> dict:
    """Return battery presence/state without spawning a subprocess where possible.

    Keys: ``present`` (bool), ``on_ac`` (Optional[bool]),
    ``discharging`` (bool), ``percent`` (Optional[float]).
    """
    status = {"present": False, "on_ac": None, "discharging": False, "percent": None}
    system = platform.system()

    if system == "Windows":
        try:
            import ctypes

            class _SPS(ctypes.Structure):
                _fields_ = [
                    ("ACLineStatus", ctypes.c_byte),
                    ("BatteryFlag", ctypes.c_byte),
                    ("BatteryLifePercent", ctypes.c_byte),
                    ("SystemStatusFlag", ctypes.c_byte),
                    ("BatteryLifeTime", ctypes.c_ulong),
                    ("BatteryFullLifeTime", ctypes.c_ulong),
                ]

            sps = _SPS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
                flag = sps.BatteryFlag & 0xFF
                ac = sps.ACLineStatus & 0xFF
                status["present"] = flag not in (128, 255)
                if ac in (0, 1):
                    status["on_ac"] = ac == 1
                status["discharging"] = status["present"] and ac == 0
                pct = sps.BatteryLifePercent & 0xFF
                if pct <= 100:
                    status["percent"] = float(pct)
        except Exception:
            pass
        return status

    if system == "Linux":
        if _is_wsl():
            # Ask the Windows host (subprocess; only on WSL).
            ps_cmd = (
                "$s = Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus "
                "-ErrorAction SilentlyContinue | Select-Object -First 1; "
                "if ($s) { "
                "[int]$s.PowerOnline.ToString().Replace('True','1').Replace('False','0'); "
                "} else { 'none' }"
            )
            try:
                out = subprocess.check_output(
                    ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                    text=True, stderr=subprocess.DEVNULL, timeout=6,
                ).strip()
                if out and out != "none":
                    status["present"] = True
                    status["on_ac"] = out.strip().endswith("1")
                    status["discharging"] = not status["on_ac"]
            except (FileNotFoundError, subprocess.TimeoutExpired,
                    subprocess.CalledProcessError, OSError):
                pass
            return status

        base = "/sys/class/power_supply"
        if os.path.isdir(base):
            try:
                for entry in sorted(os.listdir(base)):
                    bat = os.path.join(base, entry)
                    type_file = os.path.join(bat, "type")
                    if not os.path.exists(type_file):
                        continue
                    with open(type_file) as f:
                        kind = f.read().strip()
                    if kind == "Mains":
                        online = os.path.join(bat, "online")
                        if os.path.exists(online):
                            with open(online) as f:
                                status["on_ac"] = f.read().strip() == "1"
                    elif kind == "Battery":
                        status["present"] = True
                        sfile = os.path.join(bat, "status")
                        if os.path.exists(sfile):
                            with open(sfile) as f:
                                status["discharging"] = f.read().strip() == "Discharging"
                        cap = os.path.join(bat, "capacity")
                        if os.path.exists(cap):
                            with open(cap) as f:
                                try:
                                    status["percent"] = float(f.read().strip())
                                except ValueError:
                                    pass
            except OSError:
                pass
        return status

    if system == "Darwin":
        try:
            out = subprocess.check_output(
                ["pmset", "-g", "batt"], text=True,
                stderr=subprocess.DEVNULL, timeout=6,
            )
            low = out.lower()
            status["present"] = "internalbattery" in low or "%" in low
            status["on_ac"] = "ac power" in low
            status["discharging"] = "discharging" in low
        except (FileNotFoundError, subprocess.TimeoutExpired,
                subprocess.CalledProcessError, OSError):
            pass
        return status

    return status


def read_gpu_power_draw() -> Optional[float]:
    """Real-time GPU power draw in watts from the driver (works even when the
    GPU does not expose a power *limit*, e.g. many laptop GPUs). Returns watts
    or None."""
    watts = _run_first_float(
        ["nvidia-smi", "--query-gpu=power.draw",
         "--format=csv,noheader,nounits"]
    )
    if watts is not None and watts > 0:
        return watts
    # Fall back to LibreHardwareMonitor (covers AMD / Intel GPUs too).
    lhm = _read_lhm_http_powers()
    if lhm and lhm.get("gpu"):
        return lhm["gpu"]
    return None


# --- LibreHardwareMonitor / OpenHardwareMonitor HTTP (/data.json) ----------

_lhm_cache: dict = {"ts": 0.0, "data": None}

# Caches whether the Windows WMI hardware-sensor provider is available, so the
# slow PowerShell probe is not repeated on every measurement.
_win_sensor_state: dict = {"checked": 0.0, "namespace": None}
_WIN_SENSOR_RETRY = 300.0


def _lhm_value_to_watts(value: str) -> Optional[float]:
    """Parse an LHM sensor value string such as ``"23.4 W"`` into watts."""
    try:
        return float(str(value).split()[0].replace(",", "."))
    except (ValueError, IndexError, AttributeError):
        return None


def _lhm_walk(node: dict, hardware: str, out: dict) -> None:
    """Recursively collect power sensors from an LHM /data.json tree."""
    text = str(node.get("Text", ""))
    sensor_type = node.get("Type") or node.get("SensorId", "")
    children = node.get("Children", []) or []

    # Track the closest hardware-component name as we descend.
    lowered = text.lower()
    if any(k in lowered for k in ("cpu", "intel", "amd ", "ryzen", "core ")):
        hardware = "cpu"
    elif any(k in lowered for k in ("gpu", "nvidia", "geforce", "radeon", "rtx", "gtx")):
        hardware = "gpu"

    value = node.get("Value")
    if value and isinstance(value, str) and value.strip().lower().endswith("w"):
        watts = _lhm_value_to_watts(value)
        if watts is not None and watts > 0:
            name = lowered
            if hardware == "cpu" and "package" in name and out.get("cpu") is None:
                out["cpu"] = watts
            elif hardware == "gpu" and ("package" in name or "power" in name) \
                    and out.get("gpu") is None:
                out["gpu"] = watts

    for child in children:
        _lhm_walk(child, hardware, out)


def _read_lhm_http_powers() -> Optional[dict]:
    """Fetch CPU/GPU package power (W) from a running LibreHardwareMonitor /
    OpenHardwareMonitor web server. Returns ``{"cpu": w|None, "gpu": w|None}``
    or None. Result is briefly cached so a single refresh makes one request."""
    from carbon_tracker.globals import (
        LHM_HTTP_HOST,
        LHM_HTTP_PORT,
        LHM_HTTP_TIMEOUT_SEC,
    )

    now = time.time()
    if _lhm_cache["data"] is not None and (now - _lhm_cache["ts"]) < 2.0:
        return _lhm_cache["data"]
    # When the server is absent, don't re-probe on every refresh (negative cache).
    if _lhm_cache["data"] is None and (now - _lhm_cache["ts"]) < 60.0 \
            and _lhm_cache["ts"] > 0.0:
        return None

    import json
    import urllib.request

    url = "http://{}:{}/data.json".format(LHM_HTTP_HOST, LHM_HTTP_PORT)
    result = None
    try:
        with urllib.request.urlopen(url, timeout=LHM_HTTP_TIMEOUT_SEC) as resp:
            tree = json.loads(resp.read().decode("utf-8", "replace"))
        out = {"cpu": None, "gpu": None}
        _lhm_walk(tree, "", out)
        if out["cpu"] or out["gpu"]:
            result = out
    except Exception:
        result = None

    _lhm_cache["ts"] = now
    _lhm_cache["data"] = result
    return result


def _read_linux_rapl_power(interval: float = 0.2) -> Optional[float]:
    """Real CPU-package power (W) via Intel/AMD RAPL energy counters.

    Reads the cumulative ``energy_uj`` counter of every top-level powercap
    package twice over ``interval`` seconds and divides the delta by the elapsed
    time. This is the actual silicon power draw and works on AC power.
    """
    base = "/sys/class/powercap"
    if not os.path.isdir(base):
        return None
    try:
        pkgs = [
            os.path.join(base, name)
            for name in os.listdir(base)
            if name.startswith("intel-rapl:") and name.count(":") == 1
        ]
    except OSError:
        return None
    if not pkgs:
        return None

    def _energy() -> Optional[int]:
        total = 0
        for p in pkgs:
            try:
                with open(os.path.join(p, "energy_uj")) as f:
                    total += int(f.read().strip())
            except (OSError, ValueError):
                return None
        return total

    e0 = _energy()
    if e0 is None:
        return None
    time.sleep(interval)
    e1 = _energy()
    if e1 is None:
        return None

    delta = e1 - e0
    if delta < 0:  # counter wraparound
        for p in pkgs:
            try:
                with open(os.path.join(p, "max_energy_range_uj")) as f:
                    delta += int(f.read().strip())
            except (OSError, ValueError):
                pass
    if delta <= 0:
        return None
    return (delta / 1_000_000.0) / interval


def _read_windows_sensor_cpu_power() -> Optional[float]:
    """Real CPU-package power (W) from a running LibreHardwareMonitor or
    OpenHardwareMonitor instance via its WMI sensor provider. Returns None when
    neither tool is running (no extra dependency, degrades gracefully).

    Probing a WMI namespace spawns PowerShell, which is slow, so the result is
    cached: a known-good namespace is queried directly, and when none is found
    the (expensive) full probe is retried at most every ``_WIN_SENSOR_RETRY``
    seconds instead of on every measurement.
    """
    def _query(ns: str) -> Optional[float]:
        ps_cmd = (
            "Get-CimInstance -Namespace " + ns + " -ClassName Sensor "
            "-ErrorAction SilentlyContinue | Where-Object { "
            "$_.SensorType -eq 'Power' -and $_.Name -match 'Package' } | "
            "Sort-Object Value -Descending | "
            "Select-Object -First 1 -ExpandProperty Value"
        )
        watts = _run_first_float(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd]
        )
        return watts if (watts is not None and watts > 0) else None

    now = time.time()
    known = _win_sensor_state["namespace"]
    if known:
        watts = _query(known)
        if watts is not None:
            return watts
        # Lost the provider; fall through to a throttled re-probe.
        _win_sensor_state["namespace"] = None

    if (now - _win_sensor_state["checked"]) < _WIN_SENSOR_RETRY:
        return None
    _win_sensor_state["checked"] = now
    for ns in ("root/LibreHardwareMonitor", "root/OpenHardwareMonitor"):
        watts = _query(ns)
        if watts is not None:
            _win_sensor_state["namespace"] = ns
            return watts
    return None


def read_cpu_power_watts() -> Tuple[Optional[float], Optional[str]]:
    """Measure real CPU-package power in watts (works on AC power).

    Returns ``(watts, source)`` or ``(None, None)``. Uses Intel/AMD RAPL on
    Linux and a LibreHardwareMonitor/OpenHardwareMonitor sensor on Windows
    (WMI provider first, then its HTTP /data.json web server).
    """
    system = platform.system()
    if system == "Linux" and not _is_wsl():
        watts = _read_linux_rapl_power()
        if watts:
            return watts, "rapl"
    if system == "Windows":
        watts = _read_windows_sensor_cpu_power()
        if watts:
            return watts, "sensor"
    # Cross-platform: LibreHardwareMonitor / OpenHardwareMonitor web server.
    lhm = _read_lhm_http_powers()
    if lhm and lhm.get("cpu"):
        return lhm["cpu"], "lhm-http"
    return None, None



def _read_linux_battery_power() -> Optional[float]:
    """Read discharge power (W) from /sys/class/power_supply while discharging."""
    base = "/sys/class/power_supply"
    if not os.path.isdir(base):
        return None

    try:
        for entry in sorted(os.listdir(base)):
            bat = os.path.join(base, entry)
            type_file = os.path.join(bat, "type")
            if not os.path.exists(type_file):
                continue
            with open(type_file) as f:
                if f.read().strip() != "Battery":
                    continue

            # Only trust the reading while the battery is actually discharging.
            status_file = os.path.join(bat, "status")
            if os.path.exists(status_file):
                with open(status_file) as f:
                    if f.read().strip() != "Discharging":
                        continue

            # Preferred: power_now is microwatts.
            power_file = os.path.join(bat, "power_now")
            if os.path.exists(power_file):
                with open(power_file) as f:
                    micro_watts = abs(int(f.read().strip()))
                if micro_watts > 0:
                    return micro_watts / 1_000_000.0

            # Otherwise derive from current (uA) and voltage (uV).
            cur_file = os.path.join(bat, "current_now")
            volt_file = os.path.join(bat, "voltage_now")
            if os.path.exists(cur_file) and os.path.exists(volt_file):
                with open(cur_file) as f:
                    micro_amps = abs(int(f.read().strip()))
                with open(volt_file) as f:
                    micro_volts = abs(int(f.read().strip()))
                watts = (micro_amps / 1_000_000.0) * (micro_volts / 1_000_000.0)
                if watts > 0:
                    return watts
    except (OSError, ValueError):
        pass
    return None


def _read_windows_battery_power() -> Optional[float]:
    """Read discharge power (W) from the Windows WMI BatteryStatus class.

    Also used from WSL by invoking the Windows host's powershell.exe.
    """
    ps_cmd = (
        "$b = Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus "
        "-ErrorAction SilentlyContinue | Select-Object -First 1; "
        "if ($b -and $b.Discharging) { $b.DischargeRate } else { 0 }"
    )
    try:
        out = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        if out:
            milli_watts = float(out.splitlines()[0].strip())
            if milli_watts > 0:
                return milli_watts / 1000.0
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError, ValueError, OSError):
        pass
    return None


def _read_macos_battery_power() -> Optional[float]:
    """Read discharge power (W) from ioreg AppleSmartBattery."""
    try:
        out = subprocess.check_output(
            ["ioreg", "-rn", "AppleSmartBattery"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError, OSError):
        return None

    amperage = None  # mA (negative while discharging)
    voltage = None  # mV
    for line in out.splitlines():
        if '"Amperage"' in line:
            try:
                amperage = int(line.split("=")[-1].strip())
            except ValueError:
                pass
        elif '"Voltage"' in line:
            try:
                voltage = int(line.split("=")[-1].strip())
            except ValueError:
                pass

    if amperage is not None and voltage is not None and amperage < 0:
        watts = (abs(amperage) / 1000.0) * (voltage / 1000.0)
        if watts > 0:
            return watts
    return None


def read_system_power_watts() -> Tuple[Optional[float], Optional[str]]:
    """Measure instantaneous whole-system power draw from the battery.

    Returns ``(watts, source)`` or ``(None, None)`` when unavailable.
    """
    system = platform.system()

    if system == "Linux":
        if _is_wsl():
            # WSL has no battery sysfs; ask the Windows host instead.
            watts = _read_windows_battery_power()
            if watts:
                return watts, "battery-wsl"
            return None, None
        watts = _read_linux_battery_power()
        if watts:
            return watts, "battery"
        return None, None

    if system == "Windows":
        watts = _read_windows_battery_power()
        if watts:
            return watts, "battery"
        return None, None

    if system == "Darwin":
        watts = _read_macos_battery_power()
        if watts:
            return watts, "battery"
        return None, None

    return None, None
