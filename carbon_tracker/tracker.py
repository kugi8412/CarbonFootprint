#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Core Carbon Footprint Tracker.
"""

import time
import threading
from typing import Dict, List, Optional, Callable

import psutil

from carbon_tracker.models import (
    AppUsageData,
    SessionData,
    ProjectionResult,
    HardwareInfo,
    BrowserTabFilter,
)
from carbon_tracker.hardware import detect_hardware
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
                        '[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();\'  '
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
                except (
                    FileNotFoundError,
                    subprocess.TimeoutExpired,
                    subprocess.CalledProcessError,
                    OSError,
                ):
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


def _get_process_cpu_percent(names: List[str]) -> Dict[str, float]:
    """Get CPU usage for each process name. Sums across all PIDs."""
    result = {n: 0.0 for n in names}
    lower_names = {n.lower().replace(".exe", ""): n for n in names}

    # On WSL, also check Windows processes
    if _is_wsl():
        _get_wsl_windows_cpu(result, lower_names)

    for proc in psutil.process_iter(["name", "cpu_percent"]):
        try:
            pname = (proc.info["name"] or "").lower().replace(".exe", "")
            if pname in lower_names:
                result[lower_names[pname]] += proc.info["cpu_percent"] or 0.0
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return result


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


def _get_wsl_windows_cpu(result: Dict[str, float], lower_names: Dict[str, str]):
    """Query Windows process CPU usage from WSL via tasklist/powershell."""
    import subprocess

    try:
        # Use powershell.exe to get process CPU via Get-Process
        ps_cmd = (
            "Get-Process | "
            "Select-Object ProcessName, CPU | "
            "ForEach-Object { $_.ProcessName + '|' + $_.CPU }"
        )
        out = subprocess.check_output(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        for line in out.strip().splitlines():
            parts = line.strip().split("|")
            if len(parts) == 2:
                pname = parts[0].strip().lower()
                if pname in lower_names:
                    # Get-Process CPU is total CPU time in seconds, not percent
                    # Mark as running with minimal value so it gets tracked
                    if result[lower_names[pname]] == 0.0:
                        result[lower_names[pname]] = 0.1
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        OSError,
    ):
        pass


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

    # Public API
    def start(self):
        """Start monitoring."""
        if self._running:
            return None

        self._running = True
        self._start_time = time.time()

        # Prime CPU percent for psutil
        for _ in psutil.process_iter(["cpu_percent"]):
            pass

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

                per_app_cpu = _get_process_cpu_percent(apps_to_track)
                total_tracked_cpu = sum(per_app_cpu.values())

                # Build set of running process names (once per tick)
                running_procs = set()
                for proc in psutil.process_iter(["name"]):
                    try:
                        n = (proc.info["name"] or "").lower().replace(".exe", "")
                        running_procs.add(n)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                # Power estimation
                cpu_idle = self.hardware.cpu_tdp_watts * CPU_IDLE_FRACTION
                cpu_usage_frac = min(system_cpu / PERCENT_MAX, API_SLEEP_TICK_SEC)
                cpu_watts = cpu_idle + (self.hardware.cpu_tdp_watts - cpu_idle) * (
                    cpu_usage_frac**CPU_POWER_CURVE_EXPONENT
                )
                gpu_watts = self.hardware.gpu_tdp_watts * GPU_IDLE_FRACTION
                total_watts = cpu_watts + gpu_watts + self.hardware.base_system_watts

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
                k: v
                for k, v in self._app_data.items()
                if v.total_active_seconds > 0 or v.total_carbon_grams > 0
            }
            return session
