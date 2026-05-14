"""
Carbon Footprint Tracker - Python Library

Track and compute the carbon footprint of your computer usage in real-time.

Usage:
    from carbon_tracker import CarbonTracker

    tracker = CarbonTracker(apps=["firefox.exe", "code.exe"])
    tracker.start()
    # ... do work ...
    report = tracker.stop()
    print(report.summary())
"""

from carbon_tracker.globals import *
from carbon_tracker.tracker import CarbonTracker
from carbon_tracker.project import CarbonProject
from carbon_tracker.activities import Activity, ActivityTracker
from carbon_tracker.models import (
    AppUsageData,
    SessionData,
    ProjectionResult,
    HardwareInfo,
)

__version__ = "1.1.2"
__all__ = [
    "CarbonTracker",
    "CarbonProject",
    "Activity",
    "ActivityTracker",
    "AppUsageData",
    "SessionData",
    "ProjectionResult",
    "HardwareInfo",
]
