#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Project management: save/load sessions, create projects with selected files.
"""

import os
import json
import time
import uuid

from pathlib import Path
from typing import Dict, List, Optional

from carbon_tracker.models import SessionData
from carbon_tracker.activities import Activity


class CarbonProject:
    """
    A Carbon Footprint project file (.carbon.json) that stores:
    - Project metadata (name, description, selected files/apps)
    - Multiple monitoring sessions (past and current)
    - Allows computing carbon cost for past and future work

    Usage:
        project = CarbonProject("MyProject")
        project.add_session(session_data)
        project.save("my_project.carbon.json")

        # Load later
        project = CarbonProject.load("my_project.carbon.json")
        print(project.total_carbon_grams())
        print(project.project_future(hours=8))
    """

    def __init__(self, name: str = "Untitled Project", description: str = ""):
        self.name = name
        self.description = description
        self.created_at = time.time()
        self.project_id = str(uuid.uuid4())[:8]
        self.sessions: List[SessionData] = []
        self.selected_apps: List[str] = []
        self.selected_files: List[str] = []  # project source files to track context
        self.zone: str = ""
        self.api_key: str = ""
        self.tab_filters: List[dict] = []
        self.tags: List[str] = []
        self.activities: List[Activity] = []  # non-electrical activities

    def save(self, filepath: str):
        """Save project to a .carbon.json file."""
        data = {
            "version": "1.1",
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "zone": self.zone,
            "selected_apps": self.selected_apps,
            "selected_files": self.selected_files,
            "tab_filters": self.tab_filters,
            "tags": self.tags,
            "activities": [a.to_dict() for a in self.activities],
            "sessions": [s.to_dict() for s in self.sessions],
        }
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str) -> "CarbonProject":
        """Load project from a .carbon.json file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        proj = cls()
        proj.project_id = data.get("project_id", "")
        proj.name = data.get("name", "Untitled")
        proj.description = data.get("description", "")
        proj.created_at = data.get("created_at", 0)
        proj.zone = data.get("zone", "")
        proj.selected_apps = data.get("selected_apps", [])
        proj.selected_files = data.get("selected_files", [])
        proj.tab_filters = data.get("tab_filters", [])
        proj.tags = data.get("tags", [])
        proj.activities = [Activity.from_dict(a) for a in data.get("activities", [])]
        proj.sessions = [SessionData.from_dict(s) for s in data.get("sessions", [])]
        return proj

    # Session management

    def add_session(self, session: SessionData):
        """Add a completed monitoring session."""
        session.session_id = session.session_id or f"session_{int(time.time())}"
        self.sessions.append(session)

    def remove_session(self, session_id: str):
        self.sessions = [s for s in self.sessions if s.session_id != session_id]

    # Activity management

    def add_activity(self, activity: Activity):
        """Add a non-electrical activity (driving, food, etc.)."""
        self.activities.append(activity)

    def remove_activity(self, index: int):
        """Remove an activity by index."""
        if 0 <= index < len(self.activities):
            self.activities.pop(index)

    def activities_co2_grams(self) -> float:
        """Total CO2 from non-electrical activities."""
        return sum(a.co2_grams for a in self.activities)

    # Aggregation and reporting

    def total_carbon_grams(self) -> float:
        return sum(s.total_carbon_grams for s in self.sessions) + sum(
            a.co2_grams for a in self.activities
        )

    def total_energy_kwh(self) -> float:
        return sum(s.total_energy_kwh for s in self.sessions)

    def total_duration_hours(self) -> float:
        return sum(s.duration_seconds for s in self.sessions) / 3600.0

    def carbon_per_hour(self) -> float:
        hours = self.total_duration_hours()
        return self.total_carbon_grams() / hours if hours > 0.001 else 0.0

    def per_app_totals(self) -> Dict[str, dict]:
        """Aggregate per-app data across all sessions."""
        totals: Dict[str, dict] = {}
        for session in self.sessions:
            for name, app in session.apps.items():
                if name not in totals:
                    totals[name] = {
                        "total_seconds": 0.0,
                        "total_energy_kwh": 0.0,
                        "total_carbon_grams": 0.0,
                        "sessions": 0,
                    }

                totals[name]["total_seconds"] += app.total_active_seconds
                totals[name]["total_energy_kwh"] += app.total_energy_kwh
                totals[name]["total_carbon_grams"] += app.total_carbon_grams
                totals[name]["sessions"] += 1

        return totals

    def project_future(self, hours: float) -> dict:
        """Project future carbon cost based on historical data."""
        rate = self.carbon_per_hour()
        energy_hours = self.total_duration_hours()
        energy_rate = (
            self.total_energy_kwh() / energy_hours if energy_hours > 0.001 else 0.0
        )
        return {
            "projected_hours": hours,
            "projected_carbon_grams": rate * hours,
            "projected_energy_kwh": energy_rate * hours,
            "rate_grams_per_hour": rate,
            "based_on_sessions": len(self.sessions),
            "based_on_hours": energy_hours,
        }

    def summary(self) -> str:
        lines = [
            f"<== Project: {self.name} ==>",
            f"  Sessions:     {len(self.sessions)}",
            f"  Total Time:   {self.total_duration_hours():.2f} hours",
            f"  Total Energy: {self.total_energy_kwh() * 1000:.2f} Wh",
            f"  Total CO2:    {self.total_carbon_grams():.2f} g ({self.total_carbon_grams() / 1000:.4f} kg)",
            f"  Rate:         {self.carbon_per_hour():.2f} gCO2/hour",
        ]
        if self.selected_apps:
            lines.append(f"  Apps:         {', '.join(self.selected_apps)}")
        if self.selected_files:
            lines.append(f"  Files:        {len(self.selected_files)} tracked")

        app_totals = self.per_app_totals()

        if app_totals:
            lines.append(f"  <== Per-App Totals ==>")
            for name, data in sorted(
                app_totals.items(), key=lambda x: -x[1]["total_carbon_grams"]
            ):
                lines.append(
                    f"    {name:25s} "
                    f"CO2={data['total_carbon_grams']:.2f}g  "
                    f"Energy={data['total_energy_kwh'] * 1000:.2f}Wh  "
                    f"Sessions={data['sessions']}"
                )

        if self.activities:
            lines.append(
                f"  <== Non-Electrical Activities ({len(self.activities)}) ==>"
            )
            act_total = self.activities_co2_grams()
            for a in self.activities:
                lines.append(
                    f"    {a.name:28s} CO2={a.co2_grams:.1f}g  ({a.description})"
                )

            lines.append(f"    {'SUBTOTAL':28s} CO2={act_total:.1f}g")
        return "\n".join(lines)

    def add_files(self, paths: List[str]):
        """Add source files to the project context."""
        for p in paths:
            abs_p = os.path.abspath(p)
            if abs_p not in self.selected_files:
                self.selected_files.append(abs_p)

    def remove_files(self, paths: List[str]):
        abs_paths = {os.path.abspath(p) for p in paths}
        self.selected_files = [f for f in self.selected_files if f not in abs_paths]

    def scan_directory(
        self, directory: str, extensions: Optional[List[str]] = None
    ) -> List[str]:
        """
        Scan a directory for source files.
        Returns list of found files (does NOT auto-add them).
        """
        if extensions is None:
            extensions = [
                ".py",
                ".js",
                ".ts",
                ".cpp",
                ".c",
                ".h",
                ".hpp",
                ".java",
                ".cs",
                ".go",
                ".rs",
                ".rb",
                ".php",
                ".html",
                ".css",
                ".json",
                ".yaml",
                ".yml",
                ".md",
                ".txt",
                ".sh",
                ".bat",
            ]

        found = []

        for root, dirs, files in os.walk(directory):
            # Skip common non-source dirs
            dirs[:] = [
                d
                for d in dirs
                if d
                not in {
                    ".git",
                    "node_modules",
                    "__pycache__",
                    ".venv",
                    "venv",
                    "build",
                    "dist",
                    ".tox",
                    ".mypy_cache",
                }
            ]
            for fname in files:
                if any(fname.endswith(ext) for ext in extensions):
                    found.append(os.path.join(root, fname))

        return sorted(found)
