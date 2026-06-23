#! /usr/bin/env python3
# -*- coding: utf-8 -*-

# ============================================================
# HARDWARE TDP
# ============================================================
_CPU_TDP_TABLE = [
    # Intel Mobile (P - Performance 28W, U - Ultra-low power 15W)
    ("i7-14.*P", 28),
    ("i7-13.*P", 28),
    ("i7-12.*P", 28),
    ("i5-14.*P", 28),
    ("i5-13.*P", 28),
    ("i5-12.*P", 28),
    ("i7-14.*U", 15),
    ("i7-13.*U", 15),
    ("i7-12.*U", 15),
    ("i5-14.*U", 15),
    ("i5-13.*U", 15),
    ("i5-12.*U", 15),
    ("i7-14.*H", 45),
    ("i7-13.*H", 45),
    ("i5-14.*H", 45),
    ("i5-13.*H", 45),
    ("i9-14900H", 45),
    ("i9-13900H", 45),
    # Intel 11th / 10th gen mobile (H = 45W, U = 15W)
    ("i9-11.*H", 45),
    ("i7-11.*H", 45),
    ("i5-11.*H", 45),
    ("i9-10.*H", 45),
    ("i7-10.*H", 45),
    ("i5-10.*H", 45),
    ("i7-11.*U", 15),
    ("i5-11.*U", 15),
    ("i7-10.*U", 15),
    ("i5-10.*U", 15),
    # Intel Desktop & Core Ultra
    ("Core Ultra 9.*K", 125),
    ("Core Ultra 7.*K", 125),
    ("Core Ultra 5.*K", 125),
    ("Core Ultra 9", 45),
    ("Core Ultra 7", 28),
    ("Core Ultra 5", 28),
    ("i9-14900K", 125),
    ("i9-13900K", 125),
    ("i9-12900K", 125),
    ("i7-14700K", 125),
    ("i7-13700K", 125),
    ("i7-12700K", 125),
    ("i5-14600K", 125),
    ("i5-13600K", 125),
    ("i5-12600K", 125),
    ("i9-14900", 65),
    ("i9-13900", 65),
    ("i7-14700", 65),
    ("i7-13700", 65),
    ("i5-14", 65),
    ("i5-13", 65),
    ("i5-12", 65),
    ("i3-14", 60),
    ("i3-13", 60),
    ("i3-12", 60),
    # Intel 11th / 10th gen desktop
    ("i9-11900K", 125),
    ("i7-11700K", 125),
    ("i5-11600K", 125),
    ("i9-10900K", 125),
    ("i7-10700K", 125),
    ("i5-10600K", 125),
    ("i9-11", 65),
    ("i7-11", 65),
    ("i5-11", 65),
    ("i3-11", 60),
    ("i9-10", 65),
    ("i7-10", 65),
    ("i5-10", 65),
    ("i3-10", 60),
    ("Xeon", 105),
    ("Pentium", 35),
    ("Celeron", 15),
    # AMD Ryzen Mobile
    ("7840U", 28),
    ("7640U", 28),
    ("7530U", 15),
    ("6800U", 28),
    ("Ryzen 9.*HX", 55),
    ("Ryzen 7.*H", 45),
    ("Ryzen 5.*H", 45),
    # AMD Ryzen Desktop
    ("Ryzen 9.*X3D", 120),
    ("Ryzen 7.*X3D", 120),
    ("Ryzen 5.*X3D", 105),
    ("Ryzen 7 5800X3D", 105),
    ("Ryzen 9 9950X", 170),
    ("Ryzen 9 9900X", 120),
    ("Ryzen 7 9700X", 65),
    ("Ryzen 5 9600X", 65),
    ("Ryzen 9 7950X", 170),
    ("Ryzen 9 7900X", 170),
    ("Ryzen 7 7700X", 105),
    ("Ryzen 5 7600X", 105),
    ("Ryzen 9 5950X", 105),
    ("Ryzen 9 5900X", 105),
    ("Ryzen 7 5800X", 105),
    ("Ryzen 5 5600", 65),
    ("Ryzen 9", 105),
    ("Ryzen 7", 65),
    ("Ryzen 5", 65),
    ("Ryzen 3", 45),
    ("Threadripper", 280),
    # Apple Silicon
    ("M5 Max", 40),
    ("M5 Pro", 30),
    ("M5", 22),
    ("M4 Max", 40),
    ("M4 Pro", 30),
    ("M4", 22),
    ("M3 Max", 40),
    ("M3 Pro", 30),
    ("M3", 22),
    ("M2 Ultra", 60),
    ("M2 Max", 40),
    ("M2 Pro", 30),
    ("M2", 15),
    ("M1 Ultra", 60),
    ("M1 Max", 40),
    ("M1 Pro", 30),
    ("M1", 15),
]

# GPU TDP lookup
_GPU_TDP_TABLE = [
    # NVIDIA laptop GPUs - MUST precede desktop entries because a name like
    # "RTX 4070 Laptop GPU" also substring-matches the desktop "RTX 4070".
    ("RTX 4090 Laptop", 150),
    ("RTX 4080 Laptop", 150),
    ("RTX 4070 Laptop", 115),
    ("RTX 4060 Laptop", 100),
    ("RTX 4050 Laptop", 75),
    ("RTX 3080 Ti Laptop", 150),
    ("RTX 3080 Laptop", 150),
    ("RTX 3070 Ti Laptop", 125),
    ("RTX 3070 Laptop", 125),
    ("RTX 3060 Laptop", 115),
    ("RTX 3050 Ti Laptop", 75),
    ("RTX 3050 Laptop", 75),
    ("RTX 2080 Laptop", 150),
    ("RTX 2070 Laptop", 115),
    ("RTX 2060 Laptop", 90),
    # NVIDIA professional / workstation (RTX A-series and Ada)
    ("RTX A5500", 165),
    ("RTX A5000", 165),
    ("RTX A4500", 120),
    ("RTX A4000", 140),
    ("RTX A3000", 90),
    ("RTX A2000", 70),
    ("RTX A1000", 50),
    ("RTX A500", 35),
    ("RTX 5000 Ada", 175),
    ("RTX 4000 Ada", 130),
    ("RTX 3500 Ada", 120),
    ("RTX 3000 Ada", 90),
    ("RTX 2000 Ada", 70),
    # NVIDIA RTX 50
    ("RTX 5090", 575),
    ("RTX 5080", 360),
    ("RTX 5070 Ti", 300),
    ("RTX 5070", 250),
    ("RTX 5060 Ti", 160),
    ("RTX 5060", 115),
    # NVIDIA RTX 40
    ("RTX 4090", 450),
    ("RTX 4080", 320),
    ("RTX 4070 Ti", 285),
    ("RTX 4070", 200),
    ("RTX 4060 Ti", 160),
    ("RTX 4060", 115),
    # NVIDIA RTX 30
    ("RTX 3090", 350),
    ("RTX 3080", 320),
    ("RTX 3070 Ti", 290),
    ("RTX 3070", 220),
    ("RTX 3060 Ti", 200),
    ("RTX 3060", 170),
    ("RTX 3050", 130),
    # NVIDIA misc
    ("GTX 1660", 120),
    ("GTX 1650", 75),
    ("GTX 1080 Ti", 250),
    ("GTX 1080", 180),
    ("GTX 1070", 150),
    ("GTX 1060", 120),
    ("RTX", 200),
    ("GTX", 120),
    ("MX", 25),
    # AMD RX 8000 & 7000 & 6000
    ("RX 8800 XT", 260),
    ("RX 8600 XT", 150),
    ("RX 7900 XTX", 355),
    ("RX 7900 XT", 315),
    ("RX 7800 XT", 263),
    ("RX 7600", 165),
    ("RX 6900 XT", 300),
    ("RX 6800", 250),
    ("RX 6700 XT", 230),
    ("RX 6600", 132),
    # AMD Mobile / Integrated / Misc
    ("Radeon 890M", 15),
    ("Radeon 780M", 15),
    ("Radeon 680M", 15),
    ("Radeon", 150),
    # Intel Arc & Integrated
    ("Arc A770", 225),
    ("Arc A750", 225),
    ("Arc A380", 75),
    ("Intel Arc", 150),
    ("Iris Xe", 15),
    ("Intel UHD", 15),
    ("Intel HD", 10),
    ("Iris", 15),
]

# ============================================================
# EMISSION FACTORS
# https://ourworldindata.org/environmental-impacts-of-food
# https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting
# ============================================================

_VEHICLE_FACTORS = {
    "petrol_car": 120.0,  # average petrol car
    "diesel_car": 132.0,  # average diesel car
    "hybrid_car": 76.0,  # hybrid
    "electric_car": 50.0,  # EV (depends on grid, uses average)
    "motorcycle": 72.0,
    "bus": 27.0,  # per passenger-km
    "train": 6.0,  # per passenger-km (electric)
    "tram": 5.0,  # per passenger-km
    "scooter_electric": 16.0,
    "bicycle": 0.0,
    "walking": 0.0,
}

# Flights: gCO2 per passenger-km
_FLIGHT_FACTORS = {
    "economy": 133.0,
    "premium_economy": 170.0,
    "business": 234.0,
    "first": 300.0,
}

# Food: gCO2 per kg of food
_FOOD_FACTORS = {
    "beef": 27000.0,
    "lamb": 25000.0,
    "pork": 7000.0,
    "chicken": 4300.0,
    "fish": 3500.0,
    "cheese": 8500.0,
    "milk": 1200.0,  # per liter
    "eggs": 3200.0,  # per dozen (approx per kg)
    "rice": 1200.0,
    "bread": 800.0,
    "vegetables": 300.0,
    "fruit": 400.0,
    "tofu": 700.0,
    "nuts": 800.0,
    "coffee": 5000.0,  # per kg of beans
}

# Heating/cooling: gCO2 per kWh of fuel
_ENERGY_FACTORS = {
    "natural_gas": 185.0,  # gCO2/kWh
    "heating_oil": 265.0,
    "coal": 340.0,
    "wood_pellets": 25.0,
    "electricity": 400.0,  # average grid (override with zone)
    "district_heating": 130.0,
}

# Miscellaneous: gCO2 per unit
_MISC_FACTORS = {
    "paper_kg": 920.0,
    "plastic_kg": 6000.0,
    "clothing_item": 8000.0,
    "smartphone_unit": 70000.0,  # manufacturing
    "laptop_unit": 300000.0,  # manufacturing
}

# ============================================================
# FALLBACK INTENSITY VALUES (gCO2eq/kWh)
# ============================================================

# Fallback intensity values (gCO2eq/kWh) by zone: (day, night)
_FALLBACK_INTENSITY = {
    "PL": (650, 750),
    "DE": (350, 450),
    "FR": (60, 80),
    "SE": (25, 40),
    "NO": (20, 30),
    "GB": (200, 280),
    "ES": (180, 250),
    "IT": (300, 380),
    "DK": (150, 250),
    "NL": (350, 430),
    "CH": (30, 50),
    "AT": (100, 160),
    "CZ": (450, 550),
    "FI": (80, 120),
    "US-CAL": (200, 300),
    "US-NY": (250, 320),
    "US-TEX": (380, 450),
    "US-MIDA": (400, 480),
    "CA-ON": (30, 50),
    "CA-QC": (10, 15),
    "JP": (450, 530),
    "CN": (550, 650),
    "IN": (650, 720),
    "AU": (550, 650),
    "BR": (80, 120),
}

# Country code -> Electricity Maps zone
_COUNTRY_TO_ZONE = {
    "PL": "PL",
    "DE": "DE",
    "FR": "FR",
    "GB": "GB",
    "SE": "SE",
    "NO": "NO",
    "ES": "ES",
    "IT": "IT",
    "DK": "DK",
    "NL": "NL",
    "CH": "CH",
    "AT": "AT",
    "CZ": "CZ",
    "FI": "FI",
    "PT": "PT",
    "BE": "BE",
    "IE": "IE",
    "RO": "RO",
    "HU": "HU",
    "SK": "SK",
    "HR": "HR",
    "BG": "BG",
    "GR": "GR",
    "JP": "JP",
    "CN": "CN",
    "IN": "IN",
    "AU": "AU",
    "BR": "BR",
    "KR": "KR",
    "CA": "CA-ON",
    "US": "US-MIDA",
    "UA": "UA",
    "TR": "TR",
    "IL": "IL",
    "SA": "SA",
    "AE": "AE",
    "MX": "MX",
    "AR": "AR",
    "ZA": "ZA",
    "NZ": "NZ",
    "TW": "TW",
    "SG": "SG",
    "TH": "TH",
    "MY": "MY",
    "ID": "ID",
}

# ============================================================
# PyQT colour scheme (dark mode)
# ============================================================

_DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #3c3c3c;
    background-color: #252526;
}
QTabBar::tab {
    background-color: #2d2d2d;
    color: #cccccc;
    padding: 8px 18px;
    border: 1px solid #3c3c3c;
    border-bottom: none;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #1e1e1e;
    color: #ffffff;
    border-bottom: 2px solid #2ea043;
}
QTabBar::tab:hover {
    background-color: #383838;
}
QPushButton {
    background-color: #0e639c;
    color: #ffffff;
    border: none;
    padding: 6px 16px;
    border-radius: 3px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #1177bb;
}
QPushButton:disabled {
    background-color: #3c3c3c;
    color: #6e6e6e;
}
QPushButton#startBtn {
    background-color: #2ea043;
    font-size: 14px;
    padding: 8px 24px;
}
QPushButton#startBtn:hover {
    background-color: #3fb950;
}
QPushButton#stopBtn {
    background-color: #da3633;
    font-size: 14px;
    padding: 8px 24px;
}
QPushButton#stopBtn:hover {
    background-color: #f85149;
}
QPushButton#dangerBtn {
    background-color: #da3633;
}
QPushButton#dangerBtn:hover {
    background-color: #f85149;
}
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #3c3c3c;
    color: #cccccc;
    border: 1px solid #555555;
    padding: 4px 8px;
    border-radius: 3px;
}
QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #0e639c;
}
QGroupBox {
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
    color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QTreeWidget, QListWidget {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    color: #cccccc;
    alternate-background-color: #2a2d2e;
}
QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #094771;
}
QHeaderView::section {
    background-color: #333333;
    color: #cccccc;
    padding: 4px 8px;
    border: 1px solid #3c3c3c;
    font-weight: bold;
}
QScrollBar:vertical {
    background-color: #1e1e1e;
    width: 12px;
}
QScrollBar::handle:vertical {
    background-color: #424242;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #555555;
}
QCheckBox {
    spacing: 6px;
    color: #cccccc;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QStatusBar {
    background-color: #007acc;
    color: #ffffff;
}
QFrame#statCard {
    background-color: #2d2d2d;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    padding: 10px;
}
QLabel#statTitle {
    color: #888888;
    font-size: 11px;
}
QLabel#statValue {
    color: #ffffff;
    font-size: 20px;
    font-weight: bold;
}
QLabel#sectionTitle {
    color: #ffffff;
    font-size: 15px;
    font-weight: bold;
}
"""

# ==========================================
# Assumptions and constants for calculations, projections, and UI
# ==========================================

SECONDS_PER_HOUR = 3600.0
WATTS_PER_KW = 1000.0
PERCENT_MAX = 100.0

MIN_HOURS_EPSILON = 0.001

API_UPDATE_INTERVAL_SEC = 900
API_SLEEP_TICK_SEC = 1.0

CPU_POWER_CURVE_EXPONENT = 1.4
CPU_IDLE_FRACTION = 0.10
GPU_IDLE_FRACTION = 0.15
PROJECTION_CPU_LOAD_ESTIMATE = 0.30

MIN_SYSTEM_CPU_NOISE = 0.1
ACTIVE_APP_ENERGY_TAX = 0.10
BACKGROUND_APP_ENERGY_TAX = 0.02

# How often to sample the battery for real power draw (seconds). Battery reads
# can involve a subprocess (Windows/WSL/macOS), so they are throttled and cached.
POWER_MEASURE_INTERVAL_SEC = 10.0

# LibreHardwareMonitor / OpenHardwareMonitor built-in web server. When the app
# is running with "Remote Web Server" enabled, it serves all sensors as JSON at
# http://<host>:<port>/data.json. CarbonFootprint reads real CPU/GPU package
# power from it (covers AMD/Intel GPUs too). Disabled cost is one short,
# cached HTTP call per measurement interval.
LHM_HTTP_HOST = "localhost"
LHM_HTTP_PORT = 8085
LHM_HTTP_TIMEOUT_SEC = 1.0
