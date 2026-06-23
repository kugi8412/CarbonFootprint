#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Core Carbon Footprint Tracker.
"""

import time
import threading
from typing import Any, Dict, List, Optional, Callable

import psutil

from carbon_tracker.models import (
    AppUsageData,
    SessionData,
    ProjectionResult,
    HardwareInfo,
    BrowserTabFilter,
)
from carbon_tracker.hardware import detect_hardware
from carbon_tracker.power import (
    read_system_power_watts,
    read_gpu_power_draw,
    read_cpu_power_watts,
    read_battery_status,
)
from carbon_tracker.carbon_api import (
    auto_detect_zone,
    fetch_carbon_intensity,
    get_fallback_intensity,
)

from carbon_tracker.globals import (
    SECONDS_PER_HOUR,
    WATTS_PER_KW,
    PERCENT_MAX,
    MIN_HOURS_EPSILON,
    API_UPDATE_INTERVAL_SEC,
    API_SLEEP_TICK_SEC,
    CPU_POWER_CURVE_EXPONENT,
    CPU_IDLE_FRACTION,
    GPU_IDLE_FRACTION,
    PROJECTION_CPU_LOAD_ESTIMATE,
    MIN_SYSTEM_CPU_NOISE,
    BACKGROUND_APP_ENERGY_TAX,
    POWER_MEASURE_INTERVAL_SEC,
)


def _get_active_window_process() -> tuple:
    """Returns (process_name, window_title) of the foreground window."""
    import platform

    system = platform.system()

    try:
        if system == "Windows":
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ("", "")

            # Window title
            length = user32.GetWindowTextLengthW(hwnd) + 1
            buf = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hwnd, buf, length)
            title = buf.value
            # Process name
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                proc = psutil.Process(pid.value)
                return (proc.name(), title)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return ("", title)

        elif system == "Linux":
            import subprocess

            # On WSL, try to get the active Windows foreground process
            if _is_wsl():
                try:
                    ps_cmd = (
                        "$fw = (Add-Type -MemberDefinition '"
                        "[DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();'  "
                        "-Name 'Win32' -Namespace 'Native' -PassThru)::GetForegroundWindow();"
                        "$p = Get-Process | Where-Object { $_.MainWindowHandle -eq $fw } | Select-Object -First 1;"
                        "if($p){ $p.ProcessName + '|' + $p.MainWindowTitle }"
                    )
                    out = subprocess.check_output(
                        ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                        text=True,
                        stderr=subprocess.DEVNULL,
                        timeout=3,
                    ).strip()
                    if "|" in out:
                        parts = out.split("|", 1)
                        return (parts[0].strip() + ".exe", parts[1].strip())
                except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
                    pass
                return ("", "")

            out = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowname"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            pid_str = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowpid"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()

            try:
                proc = psutil.Process(int(pid_str))
                return (proc.name(), out)
            except Exception:
                return ("", out)
        elif system == "Darwin":
            import subprocess

            out = subprocess.check_output(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            return (out, "")
    except Exception:
        pass

    return ("", "")


def _scan_processes_cached(
    names: List[str],
    cache: Dict[int, list],
    wsl_state: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Return ``(per_name_cpu, running)`` using a persistent PID cache.

    Enumerating process *names* through psutil opens a handle per process and
    is very slow on Windows (~1 s for hundreds of processes). Instead we list
    PIDs (instant), resolve a name only the first time a PID appears, and keep
    the ``Process`` object in ``cache`` so ``cpu_percent`` deltas work across
    ticks. Steady-state cost is therefore proportional to the number of *new*
    processes per tick, not the total process count.
    """
    result = {n: 0.0 for n in names}
    running = set()
    lower_names = {n.lower().replace(".exe", ""): n for n in names}

    # On WSL, also check Windows processes
    if _is_wsl():
        if wsl_state is None:
            wsl_state = {}
        _get_wsl_windows_cpu(result, lower_names, running, wsl_state)

    current = set(psutil.pids())

    # Forget processes that have exited.
    for pid in [p for p in cache if p not in current]:
        del cache[pid]

    for pid in current:
        entry = cache.get(pid)
        if entry is None:
            # New PID: resolve its name once (the expensive part) and prime CPU.
            try:
                proc = psutil.Process(pid)
                name_lower = (proc.name() or "").lower().replace(".exe", "")
                proc.cpu_percent(interval=0)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                cache[pid] = None  # remember as unreadable; skip cheaply next time
                continue
            entry = [name_lower, proc]
            cache[pid] = entry
        if entry is None:
            continue

        name_lower, proc = entry
        canonical = lower_names.get(name_lower)
        if canonical is not None:
            running.add(name_lower)
            try:
                result[canonical] += proc.cpu_percent(interval=0) or 0.0
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    return result, running


def _is_wsl() -> bool:
    """Detect if running inside WSL."""
    if not hasattr(_is_wsl, "_cached"):
        _is_wsl._cached = False
        try:
            with open("/proc/version", "r") as f:
                v = f.read().lower()
                if "microsoft" in v or "wsl" in v:
                    _is_wsl._cached = True
        except OSError:
            pass
    return _is_wsl._cached


def _get_wsl_windows_cpu(
    result: Dict[str, float],
    lower_names: Dict[str, str],
    running: set,
    wsl_state: Dict[str, Any],
):
    """Measure real Windows-host process CPU% from WSL via ``powershell.exe``.

    ``Get-Process`` reports cumulative CPU *seconds* per process. We sample the
    per-name total once per tick and divide the delta by the elapsed wall-clock
    time to obtain an instantaneous percentage on the same scale as psutil's
    per-process ``cpu_percent`` (relative to a single core, so a process
    saturating N cores reports ``N * 100``). The summed delta across *all*
    processes, normalised by the host's logical-processor count, also yields the
    Windows-host system CPU% (0-100, like ``psutil.cpu_percent``), stored in
    ``wsl_state["system_cpu"]`` so the monitor loop can use it as the energy
    allocation reference instead of the WSL VM's CPU. The first sample only
    primes the baseline, so accurate values appear from the second tick onward.
    """
    import subprocess

    try:
        # Emit the host logical-processor count first, then one row per process
        # name with its summed cumulative CPU seconds.
        ps_cmd = (
            "'##NCPU|' + [Environment]::ProcessorCount; "
            "Get-Process | Group-Object ProcessName | ForEach-Object { "
            "$_.Name + '|' + (($_.Group | Measure-Object CPU -Sum).Sum) }"
        )
        out = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        OSError,
    ):
        return

    now = time.time()
    current: Dict[str, float] = {}
    for line in out.strip().splitlines():
        parts = line.strip().split("|")
        if len(parts) != 2:
            continue
        key = parts[0].strip().lower()
        if key == "##ncpu":
            try:
                ncpu = int(parts[1])
                if ncpu > 0:
                    wsl_state["ncpu"] = ncpu
            except ValueError:
                pass
            continue
        try:
            current[key] = float(parts[1])
        except ValueError:
            continue  # null CPU (e.g. protected system process)

    prev = wsl_state.get("procs")
    prev_ts = wsl_state.get("ts", 0.0)
    wsl_state["procs"] = current
    wsl_state["ts"] = now

    # Any present tracked process counts as running, even at 0% CPU.
    for pname, canonical in lower_names.items():
        if pname in current:
            running.add(pname)

    # First sample only primes the baseline; no delta available yet.
    if not prev:
        return
    elapsed = now - prev_ts
    if elapsed <= 0:
        return

    for pname, canonical in lower_names.items():
        cur = current.get(pname)
        old = prev.get(pname)
        if cur is None or old is None:
            continue
        delta = cur - old
        if delta < 0:
            delta = 0.0  # process restarted; cumulative counter reset
        percent = (delta / elapsed) * PERCENT_MAX
        if percent > result[canonical]:
            result[canonical] = percent

    # Windows-host system CPU% from the summed delta across all processes,
    # normalised by logical cores (matches psutil.cpu_percent scale: 0-100).
    ncpu = wsl_state.get("ncpu") or psutil.cpu_count() or 1
    total_delta = 0.0
    for pname, cur in current.items():
        old = prev.get(pname)
        if old is None:
            continue  # newly seen this tick; no comparable baseline
        d = cur - old
        if d > 0:
            total_delta += d
    system_cpu = (total_delta / elapsed / ncpu) * PERCENT_MAX
    wsl_state["system_cpu"] = min(max(system_cpu, 0.0), PERCENT_MAX)


class CarbonTracker:
    """
    Main Carbon Footprint Tracker.

    Usage:
        tracker = CarbonTracker(apps=["firefox.exe", "code.exe"])
        tracker.start()
        # ... do work ...
        session = tracker.stop()
        print(session.summary())
    """

    def __init__(
        self,
        apps: Optional[List[str]] = None,
        zone: Optional[str] = None,
        api_key: str = "",
        hardware: Optional[HardwareInfo] = None,
        update_interval: float = 2.0,
        tab_filters: Optional[List[BrowserTabFilter]] = None,
        on_update: Optional[Callable] = None,
    ):
        self.apps: List[str] = list(apps) if apps else []
        self.api_key = api_key
        self.update_interval = update_interval
        self.tab_filters: List[BrowserTabFilter] = (
            list(tab_filters) if tab_filters else []
        )
        self.on_update = on_update

        # Hardware detection
        if hardware:
            self.hardware = hardware
        else:
            self.hardware = detect_hardware()

        # Zone detection
        if zone:
            self.zone = zone
        else:
            detected, desc = auto_detect_zone()
            self.zone = detected if detected else "PL"

        # Internal state
        self._app_data: Dict[str, AppUsageData] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._api_thread: Optional[threading.Thread] = None
        self._start_time = 0.0
        self._total_carbon = 0.0
        self._total_energy = 0.0
        self._total_seconds = 0.0
        self._intensity = get_fallback_intensity(self.zone)
        self._intensity_real = False
        self._previous_sessions: List[SessionData] = []

        # Power measurement state. When the battery exposes a discharge rate we
        # use that real wattage; otherwise we fall back to a TDP estimate and
        # flag it so the user can be warned.
        self._power_source: Optional[str] = None
        self._power_estimated = True
        self._measured_watts: Optional[float] = None
        self._measured_gpu_watts: Optional[float] = None
        self._measured_cpu_watts: Optional[float] = None
        self._cpu_power_source: Optional[str] = None
        self._battery_status: dict = {}
        self._has_nvidia = "nvidia" in (self.hardware.gpu_name or "").lower()
        self._last_power_read = 0.0
        # PID -> [name_lower, psutil.Process] cache for the monitor loop.
        self._proc_cache: Dict[int, list] = {}
        # Persistent CPU-seconds baseline for WSL -> Windows process sampling.
        self._wsl_cpu_state: Dict[str, Any] = {}

    # Public API
    def start(self):
        """Start monitoring."""
        if self._running:
            return None

        self._running = True
        self._start_time = time.time()

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        self._api_thread = threading.Thread(target=self._api_loop, daemon=True)
        self._api_thread.start()

    def stop(self) -> SessionData:
        """Stop monitoring and return session data."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

        if self._api_thread:
            self._api_thread.join(timeout=10)

        return self._build_session()

    @property
    def is_running(self) -> bool:
        return self._running

    def add_app(self, name: str):
        with self._lock:
            lower = name.lower()
            if not any(a.lower() == lower for a in self.apps):
                self.apps.append(name)

    def remove_app(self, name: str):
        with self._lock:
            lower = name.lower()
            self.apps = [a for a in self.apps if a.lower() != lower]
            for key, data in self._app_data.items():
                if key.lower().replace(".exe", "") == lower.replace(".exe", ""):
                    data.is_active = False

    def get_app_data(self) -> Dict[str, AppUsageData]:
        with self._lock:
            return dict(self._app_data)

    def get_snapshot(self) -> dict:
        """Get current state as dict for GUI updates."""
        with self._lock:
            return {
                "running": self._running,
                "total_carbon_grams": self._total_carbon,
                "total_energy_kwh": self._total_energy,
                "total_seconds": self._total_seconds,
                "intensity": self._intensity,
                "intensity_real": self._intensity_real,
                "zone": self.zone,
                "power_source": self._power_source,
                "power_estimated": self._power_estimated,
                "apps": {k: v.to_dict() for k, v in self._app_data.items()},
                "monitored_apps": list(self.apps),
            }

    def get_session_data(self) -> SessionData:
        """Get current session data snapshot (works while running or after stop)."""
        return self._build_session()

    def add_tab_filter(self, browser: str, keyword: str):
        self.tab_filters.append(BrowserTabFilter(browser, keyword, True))

    def import_session(self, session: SessionData):
        self._previous_sessions.append(session)

    def power_warning(self) -> Optional[str]:
        """Return a user-facing warning when power is estimated, else None."""
        if not self._power_estimated:
            return None
        st = self._battery_status or read_battery_status()
        measured = []
        if self._measured_cpu_watts:
            measured.append("CPU")
        if self._measured_gpu_watts:
            measured.append("GPU")
        meas = (" " + "+".join(measured) + " measured directly;") if measured else ""
        if st.get("present") and not st.get("discharging"):
            return (
                "On AC power: the battery is not discharging, so whole-system "
                "wattage can't be read from it." + meas + " remaining components are "
                "TDP-estimated. Unplug to measure everything from the battery, or "
                "run LibreHardwareMonitor (Windows) / use RAPL (Linux) for real "
                "CPU power."
            )
        if not st.get("present"):
            return (
                "No battery detected (desktop/unsupported):" + meas + " remaining "
                "components use a TDP estimate. Values are approximate."
            )
        return (
            "Power is partly ESTIMATED from TDP heuristics." + meas
            + " Values are approximate."
        )

    def _compute_total_watts(self, system_cpu: float, now: float) -> float:
        """Total system watts.

        Priority: (1) the battery's real discharge rate (whole-system, the gold
        standard, only available while running on battery); (2) on AC, the sum
        of measured components - real GPU draw (nvidia-smi) and real CPU package
        power (RAPL / hardware sensor) - estimating only what can't be read.
        """
        # Throttle device reads (some spawn a subprocess) and cache them. Keyed
        # on the timestamp, not on _measured_watts (which stays None on AC and
        # would otherwise force a refresh every tick).
        if (
            self._last_power_read == 0.0
            or (now - self._last_power_read) >= POWER_MEASURE_INTERVAL_SEC
        ):
            # Battery state is cheap (ctypes/sysfs); only pay for the slower
            # whole-system discharge read when the battery is actually draining.
            self._battery_status = read_battery_status()
            if self._battery_status.get("discharging"):
                watts, source = read_system_power_watts()
            else:
                watts, source = None, None
            self._measured_watts = watts
            self._power_source = source
            # Real GPU draw only when an NVIDIA GPU is present (else LHM/estimate).
            self._measured_gpu_watts = (
                read_gpu_power_draw() if self._has_nvidia else None
            )
            self._measured_cpu_watts, self._cpu_power_source = read_cpu_power_watts()
            self._last_power_read = now

        # 1) Best: whole-system battery discharge (covers CPU+GPU+screen+rest).
        if self._measured_watts and self._measured_watts > 0:
            self._power_estimated = False
            self._power_source = self._power_source or "battery"
            return self._measured_watts

        # 2) On AC: assemble the total from per-component measurements, using the
        #    TDP curve only for parts the hardware won't report.
        cpu_measured = bool(self._measured_cpu_watts and self._measured_cpu_watts > 0)
        if cpu_measured:
            cpu_watts = self._measured_cpu_watts
        else:
            cpu_idle = self.hardware.cpu_tdp_watts * CPU_IDLE_FRACTION
            cpu_usage_frac = min(system_cpu / PERCENT_MAX, API_SLEEP_TICK_SEC)
            cpu_watts = cpu_idle + (self.hardware.cpu_tdp_watts - cpu_idle) * (
                cpu_usage_frac**CPU_POWER_CURVE_EXPONENT
            )

        gpu_measured = bool(self._measured_gpu_watts and self._measured_gpu_watts > 0)
        if gpu_measured:
            gpu_watts = self._measured_gpu_watts
        else:
            gpu_watts = self.hardware.gpu_tdp_watts * GPU_IDLE_FRACTION

        # Considered "measured" when both dominant dynamic components are real;
        # the base/display offset is a small fixed term.
        self._power_estimated = not (cpu_measured and gpu_measured)
        self._power_source = "components(cpu:{},gpu:{})".format(
            "meas" if cpu_measured else "est",
            "meas" if gpu_measured else "est",
        )
        return cpu_watts + gpu_watts + self.hardware.base_system_watts

    def project_future(self, hours: float) -> ProjectionResult:
        with self._lock:
            proj = ProjectionResult()
            proj.projected_hours = hours
            session_hours = self._total_seconds / SECONDS_PER_HOUR

            if session_hours > MIN_HOURS_EPSILON:
                proj.current_session_rate = self._total_carbon / session_hours
                proj.avg_energy_per_hour = self._total_energy / session_hours

            total_hist_carbon = sum(
                s.total_carbon_grams for s in self._previous_sessions
            )
            total_hist_hours = sum(
                s.duration_seconds / SECONDS_PER_HOUR for s in self._previous_sessions
            )
            if total_hist_hours > MIN_HOURS_EPSILON:
                proj.historical_rate = total_hist_carbon / total_hist_hours

            combined_carbon = self._total_carbon + total_hist_carbon
            combined_hours = session_hours + total_hist_hours
            if combined_hours > MIN_HOURS_EPSILON:
                proj.avg_carbon_per_hour = combined_carbon / combined_hours
            elif self._intensity > 0:
                total_watts = (
                    self.hardware.cpu_tdp_watts * PROJECTION_CPU_LOAD_ESTIMATE
                    + self.hardware.gpu_tdp_watts * GPU_IDLE_FRACTION
                    + self.hardware.base_system_watts
                )
                proj.avg_carbon_per_hour = (
                    total_watts / WATTS_PER_KW
                ) * self._intensity
                proj.avg_energy_per_hour = total_watts / WATTS_PER_KW

            proj.projected_carbon_grams = proj.avg_carbon_per_hour * hours
            proj.projected_energy_kwh = proj.avg_energy_per_hour * hours
            proj.total_data_sessions = len(self._previous_sessions) + (
                1 if session_hours > 0 else 0
            )
            return proj

    def _matches_tab_filter(self, app_name: str, window_title: str) -> bool:
        app_lower = app_name.lower().replace(".exe", "")
        for f in self.tab_filters:
            if not f.enabled:
                continue

            browser_lower = f.browser_process.lower().replace(".exe", "")
            if app_lower == browser_lower:
                if not window_title:
                    return False

                return f.title_filter.lower() in window_title.lower()

        return True  # no filter for this app

    def _monitor_loop(self):
        while self._running:
            try:
                active_proc, window_title = _get_active_window_process()
                system_cpu = psutil.cpu_percent(interval=0)

                with self._lock:
                    apps_to_track = list(self.apps)

                per_app_cpu, running_procs = _scan_processes_cached(
                    apps_to_track, self._proc_cache, self._wsl_cpu_state
                )
                total_tracked_cpu = sum(per_app_cpu.values())

                # On WSL, prefer the Windows-host system CPU% (derived from the
                # same Get-Process sampling) so per-app energy allocation matches
                # the host the tracked processes actually run on, not the VM.
                wsl_sys_cpu = self._wsl_cpu_state.get("system_cpu")
                if wsl_sys_cpu is not None:
                    system_cpu = wsl_sys_cpu

                # Power: measured from the battery when available, else estimated.
                total_watts = self._compute_total_watts(system_cpu, time.time())

                time_hours = self.update_interval / SECONDS_PER_HOUR
                total_energy = (total_watts / WATTS_PER_KW) * time_hours
                total_carbon = total_energy * self._intensity

                hour = time.localtime().tm_hour

                with self._lock:
                    self._total_seconds += self.update_interval
                    self._total_energy += total_energy
                    self._total_carbon += total_carbon

                    for app_name in apps_to_track:
                        app_cpu = per_app_cpu.get(app_name, 0.0)

                        # Check if running (use cached set)
                        app_lower = app_name.lower().replace(".exe", "")
                        running = app_lower in running_procs
                        if not running and app_cpu <= 0:
                            continue

                        # Check tab filter
                        if not self._matches_tab_filter(app_name, window_title):
                            active_lower = (
                                (active_proc or "").lower().replace(".exe", "")
                            )
                            if active_lower == app_lower:
                                continue

                        # Energy allocation
                        if (
                            total_tracked_cpu > MIN_SYSTEM_CPU_NOISE
                            and system_cpu > MIN_SYSTEM_CPU_NOISE
                        ):
                            cpu_share = min(
                                app_cpu / max(system_cpu, API_SLEEP_TICK_SEC),
                                API_SLEEP_TICK_SEC,
                            )
                            app_energy = total_energy * cpu_share
                        elif (
                            active_proc
                            and active_proc.lower().replace(".exe", "") == app_lower
                        ):
                            app_energy = total_energy * MIN_SYSTEM_CPU_NOISE
                        else:
                            app_energy = total_energy * BACKGROUND_APP_ENERGY_TAX

                        app_carbon = app_energy * self._intensity

                        data = self._app_data.setdefault(
                            app_name, AppUsageData(app_name=app_name)
                        )
                        data.total_active_seconds += self.update_interval
                        data.total_energy_kwh += app_energy
                        data.total_carbon_grams += app_carbon
                        data.sample_count += 1
                        data.avg_cpu_percent = (
                            data.avg_cpu_percent * (data.sample_count - 1) + app_cpu
                        ) / data.sample_count
                        data.peak_cpu_percent = max(data.peak_cpu_percent, app_cpu)
                        data.carbon_by_hour[hour] = (
                            data.carbon_by_hour.get(hour, 0.0) + app_carbon
                        )
                        data.energy_by_hour[hour] = (
                            data.energy_by_hour.get(hour, 0.0) + app_energy
                        )

                if self.on_update:
                    try:
                        self.on_update(self)
                    except Exception:
                        pass

            except Exception:
                pass

            time.sleep(self.update_interval)

    def _api_loop(self):
        while self._running:
            try:
                intensity, is_real = fetch_carbon_intensity(self.zone, self.api_key)
                with self._lock:
                    self._intensity = intensity
                    self._intensity_real = is_real
            except Exception:
                pass

            # Update every 15 minutes
            for _ in range(API_UPDATE_INTERVAL_SEC):
                if not self._running:
                    return

                time.sleep(1)

    def _build_session(self) -> SessionData:
        with self._lock:
            session = SessionData()
            session.session_id = f"session_{int(self._start_time)}"
            session.start_time = self._start_time
            session.end_time = time.time()
            session.duration_seconds = self._total_seconds
            session.total_energy_kwh = self._total_energy
            session.total_carbon_grams = self._total_carbon
            session.zone = self.zone
            session.avg_intensity = self._intensity
            session.hardware = self.hardware
            # Only include apps that have actual recorded data
            session.apps = {
                k: v for k, v in self._app_data.items()
                if v.total_active_seconds > 0 or v.total_carbon_grams > 0
            }
            return session
