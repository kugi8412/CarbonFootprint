#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Data models for Carbon Footprint Tracker.
"""

import time
import json

from typing import Dict, Optional
from dataclasses import dataclass, field


@dataclass
class HardwareInfo:
    """Auto-detected or manually configured hardware specs."""

    cpu_name: str = ""
    cpu_tdp_watts: float = 65.0
    cpu_cores: int = 4
    gpu_name: str = ""
    gpu_tdp_watts: float = 15.0
    is_laptop: bool = True
    base_system_watts: float = 20.0
    auto_detected: bool = False

    def to_dict(self) -> dict:
        return {
            "cpu_name": self.cpu_name,
            "cpu_tdp_watts": self.cpu_tdp_watts,
            "cpu_cores": self.cpu_cores,
            "gpu_name": self.gpu_name,
            "gpu_tdp_watts": self.gpu_tdp_watts,
            "is_laptop": self.is_laptop,
            "base_system_watts": self.base_system_watts,
            "auto_detected": self.auto_detected,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HardwareInfo":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AppUsageData:
    """Per-application tracking data."""

    app_name: str = ""
    total_active_seconds: float = 0.0
    total_energy_kwh: float = 0.0
    total_carbon_grams: float = 0.0
    avg_cpu_percent: float = 0.0
    peak_cpu_percent: float = 0.0
    carbon_by_hour: Dict[int, float] = field(default_factory=dict)
    energy_by_hour: Dict[int, float] = field(default_factory=dict)
    is_active: bool = True
    sample_count: int = 0

    def to_dict(self) -> dict:
        return {
            "app_name": self.app_name,
            "total_active_seconds": self.total_active_seconds,
            "total_energy_kwh": self.total_energy_kwh,
            "total_carbon_grams": self.total_carbon_grams,
            "avg_cpu_percent": self.avg_cpu_percent,
            "peak_cpu_percent": self.peak_cpu_percent,
            "carbon_by_hour": {str(k): v for k, v in self.carbon_by_hour.items()},
            "energy_by_hour": {str(k): v for k, v in self.energy_by_hour.items()},
            "is_active": self.is_active,
            "sample_count": self.sample_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AppUsageData":
        obj = cls()
        obj.app_name = d.get("app_name", "")
        obj.total_active_seconds = d.get("total_active_seconds", 0.0)
        obj.total_energy_kwh = d.get("total_energy_kwh", 0.0)
        obj.total_carbon_grams = d.get("total_carbon_grams", 0.0)
        obj.avg_cpu_percent = d.get("avg_cpu_percent", 0.0)
        obj.peak_cpu_percent = d.get("peak_cpu_percent", 0.0)
        obj.carbon_by_hour = {int(k): v for k, v in d.get("carbon_by_hour", {}).items()}
        obj.energy_by_hour = {int(k): v for k, v in d.get("energy_by_hour", {}).items()}
        obj.is_active = d.get("is_active", True)
        obj.sample_count = d.get("sample_count", 0)
        return obj


@dataclass
class SessionData:
    """Complete data for one monitoring session."""

    session_id: str = ""
    description: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration_seconds: float = 0.0
    total_energy_kwh: float = 0.0
    total_carbon_grams: float = 0.0
    zone: str = ""
    avg_intensity: float = 0.0
    hardware: Optional[HardwareInfo] = None
    apps: Dict[str, AppUsageData] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "description": self.description,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "total_energy_kwh": self.total_energy_kwh,
            "total_carbon_grams": self.total_carbon_grams,
            "zone": self.zone,
            "avg_intensity": self.avg_intensity,
            "hardware": self.hardware.to_dict() if self.hardware else None,
            "apps": {k: v.to_dict() for k, v in self.apps.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SessionData":
        obj = cls()
        obj.session_id = d.get("session_id", "")
        obj.description = d.get("description", "")
        obj.start_time = d.get("start_time", 0.0)
        obj.end_time = d.get("end_time", 0.0)
        obj.duration_seconds = d.get("duration_seconds", 0.0)
        obj.total_energy_kwh = d.get("total_energy_kwh", 0.0)
        obj.total_carbon_grams = d.get("total_carbon_grams", 0.0)
        obj.zone = d.get("zone", "")
        obj.avg_intensity = d.get("avg_intensity", 0.0)
        hw = d.get("hardware")
        obj.hardware = HardwareInfo.from_dict(hw) if hw else None
        obj.apps = {k: AppUsageData.from_dict(v) for k, v in d.get("apps", {}).items()}
        return obj

    def summary(self) -> str:
        lines = []
        lines.append(f"<== Session: {self.description or self.session_id} ==>")
        lines.append(f"  Duration:    {self.duration_seconds / 3600:.2f} hours")
        lines.append(f"  Energy:      {self.total_energy_kwh * 1000:.4f} Wh")
        lines.append(f"  CO2:         {self.total_carbon_grams:.4f} g")
        lines.append(f"  Zone:        {self.zone}")
        lines.append(f"  Intensity:   {self.avg_intensity:.1f} gCO2/kWh")
        if self.apps:
            lines.append(f"  Applications:")
            for name, app in self.apps.items():
                lines.append(
                    f"    {name:25s} "
                    f"CPU={app.avg_cpu_percent:.1f}%  "
                    f"Energy={app.total_energy_kwh * 1000:.4f}Wh  "
                    f"CO2={app.total_carbon_grams:.4f}g"
                )
        return "\n".join(lines)


@dataclass
class ProjectionResult:
    """Future carbon footprint projection."""

    projected_hours: float = 0.0
    projected_carbon_grams: float = 0.0
    projected_energy_kwh: float = 0.0
    avg_carbon_per_hour: float = 0.0
    avg_energy_per_hour: float = 0.0
    current_session_rate: float = 0.0
    historical_rate: float = 0.0
    total_data_sessions: int = 0

    def summary(self) -> str:
        return (
            f"Projection for {self.projected_hours:.1f}h: "
            f"{self.projected_carbon_grams:.2f}g CO2, "
            f"{self.projected_energy_kwh * 1000:.2f}Wh"
        )


@dataclass
class BrowserTabFilter:
    """Filter to track only specific browser tabs by title keyword."""

    browser_process: str = ""
    title_filter: str = ""
    enabled: bool = True
