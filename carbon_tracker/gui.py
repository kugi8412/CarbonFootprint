#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Carbon Footprint Tracker - GUI Application (PyQt5).

Run with: python -m carbon_tracker.gui
    or:   carbon-tracker-gui
"""

import os
import sys
import json
import time
import threading

from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QGridLayout,
        QTabWidget,
        QLabel,
        QPushButton,
        QLineEdit,
        QTextEdit,
        QCheckBox,
        QScrollArea,
        QFrame,
        QFileDialog,
        QMessageBox,
        QInputDialog,
        QDialog,
        QDialogButtonBox,
        QGroupBox,
        QSplitter,
        QListWidget,
        QListWidgetItem,
        QHeaderView,
        QTreeWidget,
        QTreeWidgetItem,
        QComboBox,
        QSpinBox,
        QDoubleSpinBox,
        QStatusBar,
        QSizePolicy,
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
    from PyQt5.QtGui import QFont, QColor, QPalette, QIcon
except ImportError:
    print("GUI requires PyQt5. Install with:")
    print("  pip install carbon-footprint-tracker[gui]")
    sys.exit(1)

from carbon_tracker.tracker import CarbonTracker
from carbon_tracker.project import CarbonProject
from carbon_tracker.models import SessionData, BrowserTabFilter

from carbon_tracker.hardware import detect_hardware
from carbon_tracker.carbon_api import auto_detect_zone

from carbon_tracker.globals import _DARK_STYLE


class StatCard(QFrame):
    """A dashboard stat card widget."""

    def __init__(self, title: str, value: str = "—", parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("statTitle")
        self._title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title_label)

        self._value_label = QLabel(value)
        self._value_label.setObjectName("statValue")
        self._value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._value_label)

    def set_value(self, text: str):
        self._value_label.setText(text)


class CarbonTrackerGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Carbon Footprint Tracker")
        self.resize(1100, 750)
        self.setMinimumSize(900, 600)

        # State
        self.tracker: Optional[CarbonTracker] = None
        self.project: Optional[CarbonProject] = None
        self.project_path: Optional[str] = None
        self.hardware = detect_hardware()
        self.zone = ""
        self.zone_desc = ""
        self._tab_filters: list = []

        # Update timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_dashboard)

        # Detect zone in background
        threading.Thread(target=self._detect_zone_bg, daemon=True).start()

        self._build_ui()

    # UI LAYOUT

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Top bar
        top = QHBoxLayout()
        title = QLabel("Carbon Footprint Tracker")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        top.addWidget(title)
        top.addStretch()
        self._status_label = QLabel("● Stopped")
        self._status_label.setStyleSheet("color: #888888; font-size: 14px;")
        top.addWidget(self._status_label)
        main_layout.addLayout(top)

        # Tabs
        self._tabs = QTabWidget()
        main_layout.addWidget(self._tabs, stretch=1)

        self._tab_dashboard = QWidget()
        self._tab_apps = QWidget()
        self._tab_project = QWidget()
        self._tab_settings = QWidget()
        self._tab_history = QWidget()

        self._tabs.addTab(self._tab_dashboard, "Dashboard")
        self._tabs.addTab(self._tab_apps, "Applications")
        self._tabs.addTab(self._tab_project, "Project && Files")
        self._tabs.addTab(self._tab_settings, "Settings")
        self._tabs.addTab(self._tab_history, "History && Forecast")
        # Note: && is QT escape for literal & in tab labels

        self._build_dashboard()
        self._build_apps_tab()
        self._build_project_tab()
        self._build_settings_tab()
        self._build_history_tab()

        # Bottom bar
        bottom = QHBoxLayout()

        self._start_btn = QPushButton("▶  Start Monitoring")
        self._start_btn.setObjectName("startBtn")
        self._start_btn.setFixedWidth(200)
        self._start_btn.clicked.connect(self._start_monitoring)
        bottom.addWidget(self._start_btn)

        self._stop_btn = QPushButton("■  Stop && Save")
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setFixedWidth(200)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_monitoring)
        bottom.addWidget(self._stop_btn)

        bottom.addStretch()

        self._zone_label = QLabel("Zone: detecting...")
        self._zone_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        bottom.addWidget(self._zone_label)

        main_layout.addLayout(bottom)

        # Status bar
        self.statusBar().showMessage("Ready")

    def _build_dashboard(self):
        layout = QVBoxLayout(self._tab_dashboard)
        layout.setContentsMargins(15, 15, 15, 15)

        # Stat cards row
        stats_row = QHBoxLayout()
        self._stat_co2 = StatCard("CO₂ Emissions", "0.000 g")
        self._stat_energy = StatCard("Energy Used", "0.000 Wh")
        self._stat_time = StatCard("Duration", "0h 00m 00s")
        self._stat_intensity = StatCard("Grid Intensity", "— gCO₂/kWh")
        for card in (
            self._stat_co2,
            self._stat_energy,
            self._stat_time,
            self._stat_intensity,
        ):
            stats_row.addWidget(card)
        layout.addLayout(stats_row)

        # Per-app table
        lbl = QLabel("Per-Application Breakdown")
        lbl.setObjectName("sectionTitle")
        layout.addWidget(lbl)

        self._app_tree = QTreeWidget()
        self._app_tree.setAlternatingRowColors(True)
        self._app_tree.setHeaderLabels(
            [
                "Application",
                "CPU avg",
                "CPU peak",
                "Energy (Wh)",
                "CO₂ (g)",
                "Time",
                "Status",
            ]
        )
        self._app_tree.setRootIsDecorated(False)
        header = self._app_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 7):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        layout.addWidget(self._app_tree, stretch=1)

    # Application tab

    def _build_apps_tab(self):
        layout = QVBoxLayout(self._tab_apps)
        layout.setContentsMargins(15, 15, 15, 15)

        # Add app row
        add_group = QGroupBox("Add Application to Monitor")
        add_layout = QHBoxLayout(add_group)

        self._app_entry = QLineEdit()
        self._app_entry.setPlaceholderText("e.g., firefox.exe, code.exe")
        self._app_entry.returnPressed.connect(self._add_app)
        add_layout.addWidget(self._app_entry, stretch=1)

        add_btn = QPushButton("Add")
        add_btn.setFixedWidth(80)
        add_btn.clicked.connect(self._add_app)
        add_layout.addWidget(add_btn)

        pick_btn = QPushButton("Pick from Running")
        pick_btn.setFixedWidth(150)
        pick_btn.clicked.connect(self._pick_running_app)
        add_layout.addWidget(pick_btn)

        layout.addWidget(add_group)

        # App list
        self._app_list = QListWidget()
        self._app_list.setAlternatingRowColors(True)
        layout.addWidget(self._app_list, stretch=1)

        app_btn_row = QHBoxLayout()
        remove_btn = QPushButton("Remove Selected")
        remove_btn.setObjectName("dangerBtn")
        remove_btn.clicked.connect(self._remove_selected_app)
        app_btn_row.addWidget(remove_btn)
        app_btn_row.addStretch()
        layout.addLayout(app_btn_row)

        # Tab filters
        filter_group = QGroupBox("Browser Tab Filters")
        filter_layout = QVBoxLayout(filter_group)

        filter_desc = QLabel(
            "Track only browser tabs containing a keyword (e.g., track Firefox only on 'GitHub')"
        )
        filter_desc.setStyleSheet("color: #888888; font-size: 11px;")
        filter_layout.addWidget(filter_desc)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Browser:"))
        self._filter_browser_entry = QLineEdit()
        self._filter_browser_entry.setPlaceholderText("firefox.exe")
        self._filter_browser_entry.setFixedWidth(150)
        filter_row.addWidget(self._filter_browser_entry)

        filter_row.addWidget(QLabel("Tab keyword:"))
        self._filter_keyword_entry = QLineEdit()
        self._filter_keyword_entry.setPlaceholderText("GitHub, Jira, StackOverflow...")
        filter_row.addWidget(self._filter_keyword_entry, stretch=1)

        filter_add_btn = QPushButton("Add Filter")
        filter_add_btn.setFixedWidth(100)
        filter_add_btn.clicked.connect(self._add_tab_filter)
        filter_row.addWidget(filter_add_btn)

        filter_layout.addLayout(filter_row)

        self._filter_list = QListWidget()
        self._filter_list.setMaximumHeight(100)
        filter_layout.addWidget(self._filter_list)

        layout.addWidget(filter_group)

    # Project and files tab

    def _build_project_tab(self):
        layout = QVBoxLayout(self._tab_project)
        layout.setContentsMargins(15, 15, 15, 15)

        # Project controls
        proj_group = QGroupBox("Project Management")
        proj_layout = QVBoxLayout(proj_group)

        btn_row = QHBoxLayout()
        for text, slot in [
            ("New Project", self._new_project),
            ("Open Project", self._open_project),
            ("Save Project", self._save_project),
        ]:
            btn = QPushButton(text)
            btn.setFixedWidth(150)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        proj_layout.addLayout(btn_row)

        self._project_info_label = QLabel("No project loaded.")
        self._project_info_label.setStyleSheet("color: #aaaaaa;")
        proj_layout.addWidget(self._project_info_label)

        layout.addWidget(proj_group)

        # File selection
        files_group = QGroupBox("Project Source Files")
        files_layout = QVBoxLayout(files_group)

        files_desc = QLabel(
            "Select files to associate with this project (for context and reporting)."
        )
        files_desc.setStyleSheet("color: #888888; font-size: 11px;")
        files_layout.addWidget(files_desc)

        file_btn_row = QHBoxLayout()
        for text, slot in [
            ("Add Files...", self._add_files),
            ("Scan Directory...", self._scan_directory),
        ]:
            btn = QPushButton(text)
            btn.setFixedWidth(160)
            btn.clicked.connect(slot)
            file_btn_row.addWidget(btn)

        remove_files_btn = QPushButton("Remove Selected")
        remove_files_btn.setObjectName("dangerBtn")
        remove_files_btn.setFixedWidth(160)
        remove_files_btn.clicked.connect(self._remove_selected_files)
        file_btn_row.addWidget(remove_files_btn)
        file_btn_row.addStretch()
        files_layout.addLayout(file_btn_row)

        self._file_list = QListWidget()
        self._file_list.setAlternatingRowColors(True)
        self._file_list.setSelectionMode(QListWidget.MultiSelection)
        files_layout.addWidget(self._file_list, stretch=1)

        layout.addWidget(files_group, stretch=1)

    # Settings Tab

    def _build_settings_tab(self):
        layout = QVBoxLayout(self._tab_settings)
        layout.setContentsMargins(15, 15, 15, 15)

        # Hardware
        hw_group = QGroupBox("Hardware Configuration (auto-detected)")
        hw_grid = QGridLayout(hw_group)

        self._hw_fields = {}
        fields = [
            ("CPU", self.hardware.cpu_name or "(not detected)"),
            ("CPU TDP (W)", str(self.hardware.cpu_tdp_watts)),
            ("GPU", self.hardware.gpu_name or "(not detected)"),
            ("GPU TDP (W)", str(self.hardware.gpu_tdp_watts)),
            ("Base System (W)", str(self.hardware.base_system_watts)),
        ]
        for i, (label, value) in enumerate(fields):
            hw_grid.addWidget(QLabel(f"{label}:"), i, 0)
            entry = QLineEdit(value)
            entry.setMinimumWidth(300)
            hw_grid.addWidget(entry, i, 1)
            self._hw_fields[label] = entry

        self._laptop_check = QCheckBox("Laptop (has battery)")
        self._laptop_check.setChecked(self.hardware.is_laptop)
        hw_grid.addWidget(self._laptop_check, len(fields), 0, 1, 2)

        redetect_btn = QPushButton("Re-detect Hardware")
        redetect_btn.setFixedWidth(160)
        redetect_btn.clicked.connect(self._redetect_hardware)
        hw_grid.addWidget(redetect_btn, len(fields) + 1, 0, 1, 2)

        layout.addWidget(hw_group)

        # Zone / API
        zone_group = QGroupBox("Carbon Intensity")
        zone_grid = QGridLayout(zone_group)

        zone_grid.addWidget(QLabel("Zone:"), 0, 0)
        self._zone_entry = QLineEdit()
        self._zone_entry.setPlaceholderText("PL, DE, US-CAL...")
        if self.zone:
            self._zone_entry.setText(self.zone)
        zone_grid.addWidget(self._zone_entry, 0, 1)

        zone_detect_btn = QPushButton("Auto-detect")
        zone_detect_btn.setFixedWidth(120)
        zone_detect_btn.clicked.connect(self._detect_zone_ui)
        zone_grid.addWidget(zone_detect_btn, 0, 2)

        zone_grid.addWidget(QLabel("API Key:"), 1, 0)
        self._apikey_entry = QLineEdit()
        self._apikey_entry.setPlaceholderText("(optional) Electricity Maps key")
        self._apikey_entry.setEchoMode(QLineEdit.Password)
        zone_grid.addWidget(self._apikey_entry, 1, 1, 1, 2)

        zone_grid.addWidget(QLabel("Interval (s):"), 2, 0)
        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.5, 60.0)
        self._interval_spin.setValue(2.0)
        self._interval_spin.setSingleStep(0.5)
        zone_grid.addWidget(self._interval_spin, 2, 1)

        layout.addWidget(zone_group)
        layout.addStretch()

    # History & Forecast Tab

    def _build_history_tab(self):
        layout = QVBoxLayout(self._tab_history)
        layout.setContentsMargins(15, 15, 15, 15)

        lbl = QLabel("Session History & Carbon Forecast")
        lbl.setObjectName("sectionTitle")
        layout.addWidget(lbl)

        self._history_text = QTextEdit()
        self._history_text.setReadOnly(True)
        self._history_text.setFont(QFont("Consolas", 11))
        self._history_text.setPlainText(
            "Load a project to see session history and forecasts.\n"
        )
        layout.addWidget(self._history_text, stretch=1)

        forecast_row = QHBoxLayout()

        forecast_row.addWidget(QLabel("Forecast future carbon cost:"))
        self._forecast_hours_spin = QDoubleSpinBox()
        self._forecast_hours_spin.setRange(0.1, 10000.0)
        self._forecast_hours_spin.setValue(8.0)
        self._forecast_hours_spin.setSingleStep(1.0)
        self._forecast_hours_spin.setFixedWidth(100)
        forecast_row.addWidget(self._forecast_hours_spin)

        forecast_btn = QPushButton("Forecast")
        forecast_btn.setFixedWidth(100)
        forecast_btn.clicked.connect(self._do_forecast)
        forecast_row.addWidget(forecast_btn)

        forecast_row.addStretch()

        import_btn = QPushButton("Import Session File...")
        import_btn.setFixedWidth(170)
        import_btn.clicked.connect(self._import_session_file)
        forecast_row.addWidget(import_btn)

        layout.addLayout(forecast_row)

    # ACTIONS

    def _detect_zone_bg(self):
        zone, desc = auto_detect_zone()
        if zone:
            self.zone = zone
            self.zone_desc = desc
            QTimer.singleShot(0, lambda: self._on_zone_detected(zone, desc))
        else:
            QTimer.singleShot(
                0, lambda: self._zone_label.setText("Zone: not detected (set manually)")
            )

    def _on_zone_detected(self, zone: str, desc: str):
        self._zone_label.setText(f"Zone: {zone} ({desc})")
        if not self._zone_entry.text():
            self._zone_entry.setText(zone)

    def _detect_zone_ui(self):
        threading.Thread(target=self._detect_zone_bg, daemon=True).start()

    def _get_monitored_apps(self) -> list:
        apps = []
        for i in range(self._app_list.count()):
            item = self._app_list.item(i)
            if item.checkState() == Qt.Checked:
                apps.append(item.text())
        return apps

    def _add_app(self):
        name = self._app_entry.text().strip()
        if not name:
            return
        self._app_entry.clear()
        self._add_app_item(name, checked=True)

    def _add_app_item(self, name: str, checked: bool = True):
        # Check for duplicates
        for i in range(self._app_list.count()):
            if self._app_list.item(i).text() == name:
                return None

        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._app_list.addItem(item)

    def _remove_selected_app(self):
        for item in self._app_list.selectedItems():
            name = item.text()
            row = self._app_list.row(item)
            self._app_list.takeItem(row)
            if self.tracker and self.tracker.is_running:
                self.tracker.remove_app(name)

    def _pick_running_app(self):
        try:
            import psutil

            procs = set()
            _ignore = {
                "system",
                "idle",
                "svchost.exe",
                "conhost.exe",
                "csrss.exe",
                "dwm.exe",
                "lsass.exe",
                "smss.exe",
                "wininit.exe",
                "winlogon.exe",
                "services.exe",
                "runtimebroker.exe",
                "searchhost.exe",
            }
            for proc in psutil.process_iter(["name"]):
                try:
                    n = proc.info["name"]
                    if n and n.lower() not in _ignore:
                        procs.add(n)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            dlg = QDialog(self)
            dlg.setWindowTitle("Select Running Applications")
            dlg.resize(400, 500)
            dlg_layout = QVBoxLayout(dlg)

            dlg_layout.addWidget(QLabel("Select apps to monitor:"))

            proc_list = QListWidget()
            proc_list.setAlternatingRowColors(True)
            proc_list.setSelectionMode(QListWidget.MultiSelection)
            for name in sorted(procs):
                proc_list.addItem(name)
            dlg_layout.addWidget(proc_list, stretch=1)

            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            dlg_layout.addWidget(buttons)

            if dlg.exec_() == QDialog.Accepted:
                for item in proc_list.selectedItems():
                    self._add_app_item(item.text(), checked=True)
                    if self.tracker and self.tracker.is_running:
                        self.tracker.add_app(item.text())

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _add_tab_filter(self):
        browser = self._filter_browser_entry.text().strip()
        keyword = self._filter_keyword_entry.text().strip()
        if not browser or not keyword:
            return
        self._filter_browser_entry.clear()
        self._filter_keyword_entry.clear()

        self._tab_filters.append(BrowserTabFilter(browser, keyword))
        self._filter_list.addItem(f'{browser} → "{keyword}"')

        if self.tracker:
            self.tracker.add_tab_filter(browser, keyword)

    # ---- Start / Stop ----

    def _read_settings(self):
        try:
            self.hardware.cpu_tdp_watts = float(self._hw_fields["CPU TDP (W)"].text())
        except ValueError:
            pass
        try:
            self.hardware.gpu_tdp_watts = float(self._hw_fields["GPU TDP (W)"].text())
        except ValueError:
            pass
        try:
            self.hardware.base_system_watts = float(
                self._hw_fields["Base System (W)"].text()
            )
        except ValueError:
            pass
        self.hardware.is_laptop = self._laptop_check.isChecked()

        zone_text = self._zone_entry.text().strip()
        if zone_text:
            self.zone = zone_text

    def _start_monitoring(self):
        apps = self._get_monitored_apps()
        if not apps:
            QMessageBox.warning(
                self,
                "No Apps",
                "Add at least one application to monitor.\nGo to the Applications tab.",
            )
            return

        self._read_settings()
        interval = self._interval_spin.value()

        self.tracker = CarbonTracker(
            apps=apps,
            zone=self.zone,
            api_key=self._apikey_entry.text().strip(),
            hardware=self.hardware,
            update_interval=interval,
            tab_filters=list(self._tab_filters),
        )
        self.tracker.start()

        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_label.setText("● Monitoring")
        self._status_label.setStyleSheet("color: #3fb950; font-size: 14px;")
        self.statusBar().showMessage("Monitoring active...")

        self._timer.start(2000)

    def _stop_monitoring(self):
        if not self.tracker:
            return

        self._timer.stop()
        session = self.tracker.stop()
        self.tracker = None

        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status_label.setText("● Stopped")
        self._status_label.setStyleSheet("color: #888888; font-size: 14px;")
        self.statusBar().showMessage("Monitoring stopped.")

        # Auto-save to project
        if self.project:
            session.description = (
                f"{self.project.name} session #{len(self.project.sessions) + 1}"
            )
            self.project.add_session(session)
            if self.project_path:
                self.project.save(self.project_path)
            self._refresh_history()

        # Always save a standalone report JSON
        report_path = self._save_session_report(session)

        summary = session.summary()
        if report_path:
            summary += f"\n\nReport saved to:\n{report_path}"
        QMessageBox.information(self, "Session Complete", summary)

    def _save_session_report(self, session: SessionData) -> str:
        """Save session data as a standalone JSON report. Returns the file path or empty string."""
        try:
            timestamp = time.strftime(
                "%Y%m%d_%H%M%S", time.localtime(session.start_time)
            )
            filename = f"carbon_report_{timestamp}.json"

            # Save next to the project file if one is open, otherwise in current dir
            if self.project_path:
                directory = os.path.dirname(self.project_path)
            else:
                directory = os.getcwd()

            path = os.path.join(directory, filename)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
            self.statusBar().showMessage(f"Report saved: {path}", 8000)
            return path
        except Exception as e:
            self.statusBar().showMessage(f"Failed to save report: {e}", 8000)
            return ""

    def _update_dashboard(self):
        if not self.tracker:
            return
        snap = self.tracker.get_snapshot()

        carbon = snap["total_carbon_grams"]
        energy = snap["total_energy_kwh"] * 1000
        elapsed = snap["total_seconds"]
        intensity = snap["intensity"]

        h = int(elapsed) // 3600
        m = (int(elapsed) % 3600) // 60
        s = int(elapsed) % 60

        self._stat_co2.set_value(f"{carbon:.4f} g")
        self._stat_energy.set_value(f"{energy:.4f} Wh")
        self._stat_time.set_value(f"{h}h {m:02d}m {s:02d}s")
        live_marker = "(live)" if snap["intensity_real"] else "(est.)"
        self._stat_intensity.set_value(f"{intensity:.0f} gCO₂/kWh {live_marker}")

        # Update per-app table
        self._app_tree.clear()
        apps = snap.get("apps", {})
        monitored = snap.get("monitored_apps", [])

        # Show all monitored apps, even if not yet detected
        shown = set()
        for name, data in apps.items():
            shown.add(name)
            active_sec = data.get("total_active_seconds", 0)
            ah = int(active_sec) // 3600
            am = (int(active_sec) % 3600) // 60
            status = "active" if data.get("is_active", True) else "removed"
            item = QTreeWidgetItem(
                [
                    name,
                    f"{data.get('avg_cpu_percent', 0):.1f}%",
                    f"{data.get('peak_cpu_percent', 0):.1f}%",
                    f"{data.get('total_energy_kwh', 0) * 1000:.4f}",
                    f"{data.get('total_carbon_grams', 0):.4f}",
                    f"{ah}h{am:02d}m",
                    status,
                ]
            )
            self._app_tree.addTopLevelItem(item)

        # Add monitored apps that haven't been detected yet
        for name in monitored:
            if name not in shown:
                item = QTreeWidgetItem([name, "—", "—", "—", "—", "0h00m", "waiting"])
                self._app_tree.addTopLevelItem(item)

        self.statusBar().showMessage(
            f"CO₂: {carbon:.3f}g | Energy: {energy:.3f}Wh | "
            f"Zone: {snap['zone']} | Intensity: {intensity:.0f} gCO₂/kWh"
        )

    # ---- Project management ----

    def _new_project(self):
        name, ok = QInputDialog.getText(self, "New Project", "Project name:")
        if not ok or not name:
            return
        self.project = CarbonProject(name=name)
        self.project.selected_apps = self._get_monitored_apps()
        self.project.zone = self.zone
        self.project_path = None
        self._project_info_label.setText(f"Project: {name} (unsaved)")
        self._refresh_file_list()

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Carbon Project (*.carbon.json);;All files (*.*)"
        )
        if not path:
            return
        try:
            self.project = CarbonProject.load(path)
            self.project_path = path
            self._project_info_label.setText(
                f"Project: {self.project.name} | {len(self.project.sessions)} sessions | "
                f"{self.project.total_carbon_grams():.2f}g CO₂ total"
            )
            for app in self.project.selected_apps:
                self._add_app_item(app, checked=True)
            if self.project.zone:
                self.zone = self.project.zone
                self._zone_entry.setText(self.zone)
            self._refresh_file_list()
            self._refresh_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load project:\n{e}")

    def _save_project(self):
        if not self.project:
            QMessageBox.warning(self, "No Project", "Create or open a project first.")
            return
        self.project.selected_apps = self._get_monitored_apps()
        self.project.zone = self.zone
        if not self.project_path:
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Project",
                f"{self.project.name}.carbon.json",
                "Carbon Project (*.carbon.json)",
            )
            if not path:
                return
            self.project_path = path
        self.project.save(self.project_path)
        self._project_info_label.setText(
            f"Project: {self.project.name} | Saved to {os.path.basename(self.project_path)}"
        )

    # ---- File selection ----

    def _add_files(self):
        if not self.project:
            QMessageBox.warning(self, "No Project", "Create or open a project first.")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Select source files")
        if paths:
            self.project.add_files(paths)
            self._refresh_file_list()

    def _scan_directory(self):
        if not self.project:
            QMessageBox.warning(self, "No Project", "Create or open a project first.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Select directory to scan")
        if not directory:
            return

        # Extension picker dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Select file types to include")
        dlg.resize(350, 420)
        dlg_layout = QVBoxLayout(dlg)

        dlg_layout.addWidget(QLabel("File extensions to scan:"))

        exts = [
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
        default_checked = {
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
        }

        ext_checks = {}
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        for ext in exts:
            cb = QCheckBox(ext)
            cb.setChecked(ext in default_checked)
            scroll_layout.addWidget(cb)
            ext_checks[ext] = cb
        scroll_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        dlg_layout.addWidget(scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        dlg_layout.addWidget(buttons)

        if dlg.exec_() != QDialog.Accepted:
            return

        selected_exts = [e for e, cb in ext_checks.items() if cb.isChecked()]
        found = self.project.scan_directory(directory, selected_exts)

        if not found:
            QMessageBox.information(self, "Scan", "No matching files found.")
            return

        self._show_scan_results(found)

    def _show_scan_results(self, found: list):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Found {len(found)} files")
        dlg.resize(600, 500)
        dlg_layout = QVBoxLayout(dlg)

        dlg_layout.addWidget(QLabel(f"Found {len(found)} files. Select which to add:"))

        file_list = QListWidget()
        file_list.setAlternatingRowColors(True)
        file_list.setSelectionMode(QListWidget.MultiSelection)
        for fpath in found:
            short = os.path.relpath(fpath)
            item = QListWidgetItem(short)
            item.setData(Qt.UserRole, fpath)
            item.setSelected(True)
            file_list.addItem(item)
        dlg_layout.addWidget(file_list, stretch=1)

        sel_row = QHBoxLayout()
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(file_list.selectAll)
        sel_row.addWidget(sel_all_btn)
        desel_btn = QPushButton("Deselect All")
        desel_btn.clicked.connect(file_list.clearSelection)
        sel_row.addWidget(desel_btn)
        sel_row.addStretch()
        dlg_layout.addLayout(sel_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        dlg_layout.addWidget(buttons)

        if dlg.exec_() == QDialog.Accepted:
            selected = [item.data(Qt.UserRole) for item in file_list.selectedItems()]
            self.project.add_files(selected)
            self._refresh_file_list()

    def _remove_selected_files(self):
        if not self.project:
            return
        to_remove = []
        for item in self._file_list.selectedItems():
            to_remove.append(item.data(Qt.UserRole))
        if to_remove:
            self.project.remove_files(to_remove)
            self._refresh_file_list()

    def _refresh_file_list(self):
        self._file_list.clear()
        if not self.project:
            return
        for fpath in self.project.selected_files:
            short = os.path.relpath(fpath) if os.path.isabs(fpath) else fpath
            item = QListWidgetItem(short)
            item.setData(Qt.UserRole, fpath)
            self._file_list.addItem(item)

    # ---- History & Forecast ----

    def _refresh_history(self):
        self._history_text.clear()
        if not self.project:
            self._history_text.setPlainText("No project loaded.\n")
            return
        self._history_text.setPlainText(self.project.summary())

    def _do_forecast(self):
        if not self.project or not self.project.sessions:
            QMessageBox.warning(
                self, "No Data", "Need at least one saved session to forecast."
            )
            return
        hours = self._forecast_hours_spin.value()
        result = self.project.project_future(hours)
        msg = (
            f"\n<== FORECAST for {result['projected_hours']:.1f} hours ==>\n"
            f"  Projected CO₂:    {result['projected_carbon_grams']:.2f} g\n"
            f"  Projected Energy: {result['projected_energy_kwh'] * 1000:.2f} Wh\n"
            f"  Rate:             {result['rate_grams_per_hour']:.2f} gCO₂/hour\n"
            f"  Based on:         {result['based_on_sessions']} sessions "
            f"({result['based_on_hours']:.1f}h of data)\n"
        )

        # Equivalences
        km_driving = result["projected_carbon_grams"] / 120.0
        phone_charges = result["projected_energy_kwh"] / 0.01
        tree_days = result["projected_carbon_grams"] / 60.0
        msg += (
            f"\n  Equivalences:\n"
            f"    - Driving a car:     {km_driving:.4f} km\n"
            f"    - Phone charges:     {phone_charges:.2f} charges\n"
            f"    - Tree absorption:   {tree_days:.3f} tree-days to offset\n"
        )

        # Energy saving recommendations
        msg += "\n<== ENERGY SAVING RECOMMENDATIONS ==>\n"

        intensity = 0.0
        if self.project.sessions:
            intensity = self.project.sessions[-1].avg_intensity

        if intensity > 500:
            msg += (
                f"  [!] Your grid has HIGH carbon intensity ({intensity:.0f} gCO₂/kWh).\n"
                f"      Consider scheduling heavy workloads at times with more renewables.\n"
                f"      Typical low-carbon hours: 10:00-16:00 (solar) or windy periods.\n"
            )
        elif intensity > 200:
            msg += (
                f"  [i] Your grid has MODERATE carbon intensity ({intensity:.0f} gCO₂/kWh).\n"
                f"      Shifting compute to off-peak hours can help reduce emissions.\n"
            )
        else:
            msg += f"  [+] Your grid has LOW carbon intensity ({intensity:.0f} gCO₂/kWh). Great!\n"

        if result["based_on_hours"] > 8:
            msg += (
                f"  [!] Long total working time ({result['based_on_hours']:.1f}h).\n"
                f"      Consider taking breaks to reduce continuous power consumption.\n"
            )

        msg += (
            "\n  General tips to reduce your carbon footprint:\n"
            "    - Lower screen brightness to 50% (saves ~10-20% display energy)\n"
            "    - Close unused applications and browser tabs\n"
            "    - Use sleep/hibernate mode during breaks\n"
            "    - Schedule heavy builds/training during low-intensity grid hours\n"
            "    - Prefer wired connections over WiFi when possible\n"
            "    - Keep system drivers and power management up-to-date\n"
        )

        self._history_text.append(msg)

    def _import_session_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Session",
            "",
            "Carbon Project (*.carbon.json);;JSON (*.json);;All (*.*)",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            if not self.project:
                self.project = CarbonProject(name="Imported")

            if "sessions" in data:
                for s in data["sessions"]:
                    self.project.add_session(SessionData.from_dict(s))
            elif "session_id" in data:
                self.project.add_session(SessionData.from_dict(data))

            self._refresh_history()
            QMessageBox.information(self, "Import", "Session(s) imported successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    # Settings actions

    def _redetect_hardware(self):
        self.hardware = detect_hardware()
        self._hw_fields["CPU"].setText(self.hardware.cpu_name or "(not detected)")
        self._hw_fields["CPU TDP (W)"].setText(str(self.hardware.cpu_tdp_watts))
        self._hw_fields["GPU"].setText(self.hardware.gpu_name or "(not detected)")
        self._hw_fields["GPU TDP (W)"].setText(str(self.hardware.gpu_tdp_watts))
        self._hw_fields["Base System (W)"].setText(str(self.hardware.base_system_watts))
        self._laptop_check.setChecked(self.hardware.is_laptop)
        self.statusBar().showMessage("Hardware re-detected.", 5000)

    def closeEvent(self, event):
        if self.tracker and self.tracker.is_running:
            reply = QMessageBox.question(
                self,
                "Monitoring Active",
                "Monitoring is still running. Stop and save before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Yes:
                self._stop_monitoring()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(_DARK_STYLE)
    window = CarbonTrackerGUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
