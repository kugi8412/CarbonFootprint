#! /usr/bin/env python3
# -*- coding: utf-8 -*-

# ============================================================
# HARDWARE TDP
# ============================================================
_CPU_TDP_TABLE = [
    # Intel Mobile 10th-14th gen (HX 55W, H 45W, P 28W, U 15W, G-series 28W)
    (r"i[3579]-1[0-4]\d+HX", 55),
    (r"i[57]-113\d\dH", 35),  # 11th gen H35 (i7-11370H, i5-11320H)
    (r"i[3579]-1[0-4]\d+H", 45),
    (r"i[3579]-1[0-4]\d+P", 28),
    (r"i[3579]-1[0-4]\d+U", 15),
    (r"i[3579]-1[0-4]\d+G\d", 28),
    # Intel Core Ultra (reported as "Core(TM) Ultra 7 155H")
    (r"Ultra [579] \d+K", 125),
    (r"Ultra [579] \d+HX", 55),
    (r"Ultra 9 \d+H", 45),
    (r"Ultra [57] \d+H", 28),
    (r"Ultra [579] \d+U", 15),
    (r"Ultra [579] \d+V", 17),
    ("Ultra 9", 45),
    ("Ultra 7", 28),
    ("Ultra 5", 28),
    # Intel Desktop
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
    (r"Ryzen [3579] \d+HX", 55),
    (r"Ryzen [3579] \d+H", 45),
    (r"Ryzen [3579] \d+U", 28),
    ("Ryzen AI", 28),
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
    ("RTX 5090 Laptop", 175),
    ("RTX 5080 Laptop", 175),
    ("RTX 5070 Ti Laptop", 140),
    ("RTX 5070 Laptop", 115),
    ("RTX 5060 Laptop", 115),
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
    (r"Radeon\(TM\) Graphics", 15),
    ("Radeon Graphics", 15),
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
# DATA-CENTER / HPC CPU: (pattern, package TDP W, physical cores per socket)
# ============================================================
_HPC_CPU_TDP_TABLE = [
    ("E5-2697 v3", 145, 14),
    ("E5-2697 v4", 145, 18),
    ("E5-2698 v3", 135, 16),
    ("E5-2690 v3", 135, 12),
    ("E5-2690 v4", 135, 14),
    ("E5-2680 v3", 120, 12),
    ("E5-2680 v4", 120, 14),
    ("E5-2670 v3", 120, 12),
    ("E5-2650 v4", 105, 12),
    ("E5-2630 v4", 85, 10),
    ("Gold 6148", 150, 20),
    ("Gold 6248", 150, 20),
    ("Gold 6130", 125, 16),
    ("Gold 6230", 125, 20),
    ("Platinum 8280", 205, 28),
    ("Platinum 8380", 270, 40),
    ("Platinum 8480", 350, 56),
    ("EPYC 7742", 225, 64),
    ("EPYC 7763", 280, 64),
    ("EPYC 7543", 225, 32),
    ("EPYC 9254", 200, 24),
    ("EPYC 9654", 360, 96),
]

# ============================================================
# DATA-CENTER / HPC ACCELERATOR TDP (board power, watts)
# Used when a job runs on a shared compute node where the consumer GPU table
# above does not apply. Ordered most-specific first.
# ============================================================
_HPC_GPU_TDP_TABLE = [
    # NVIDIA data-center (Hopper / Blackwell)
    ("GB200", 1200),
    ("B200", 1000),
    ("B100", 700),
    ("H200", 700),
    ("H100", 700),
    ("H800", 350),
    ("GH200", 1000),
    # NVIDIA Ampere
    ("A100", 400),
    ("A800", 400),
    ("A40", 300),
    ("A30", 165),
    ("A10", 150),
    ("A16", 250),
    # NVIDIA Ada / Lovelace data-center
    ("L40S", 350),
    ("L40", 300),
    ("L4", 72),
    # NVIDIA Volta / Pascal / Turing data-center
    ("V100", 300),
    ("P100", 250),
    ("P40", 250),
    ("T4", 70),
    ("K80", 300),
    ("K40", 235),
    # AMD Instinct
    ("MI300X", 750),
    ("MI300A", 760),
    ("MI250X", 560),
    ("MI250", 560),
    ("MI210", 300),
    ("MI100", 300),
    ("MI50", 300),
    # Intel Data Center GPU
    ("Max 1550", 600),
    ("Max 1100", 300),
    # Google / generic accelerators (approximate board power)
    ("TPU v4", 200),
    ("TPU v3", 220),
    ("TPU v2", 280),
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

# Fallback intensity values (gCO2eq/kWh) by country: lifecycle annual averages
# from Ember, Yearly Electricity Data (via Our World in Data), 2025 or the
# latest year available. Sub-national zones (US-CAL-CISO, CA-ON) use their
# country's value.
_FALLBACK_INTENSITY = {
    "AE": 468,
    "AR": 346,
    "AT": 117,
    "AU": 525,
    "BE": 150,
    "BG": 276,
    "BR": 110,
    "CA": 191,
    "CH": 39,
    "CL": 289,
    "CN": 525,
    "CZ": 401,
    "DE": 330,
    "DK": 114,
    "EE": 319,
    "EG": 563,
    "ES": 154,
    "FI": 57,
    "FR": 41,
    "GB": 217,
    "GR": 315,
    "HR": 158,
    "HU": 163,
    "ID": 680,
    "IE": 257,
    "IL": 493,
    "IN": 670,
    "IT": 285,
    "JP": 477,
    "KR": 417,
    "LT": 138,
    "LV": 139,
    "MX": 474,
    "MY": 602,
    "NL": 254,
    "NO": 28,
    "NZ": 93,
    "PH": 588,
    "PL": 589,
    "PT": 128,
    "RO": 251,
    "SA": 692,
    "SE": 35,
    "SG": 497,
    "SI": 183,
    "SK": 95,
    "TH": 546,
    "TR": 475,
    "TW": 633,
    "UA": 250,
    "US": 384,
    "VN": 461,
    "ZA": 699,
}

# Zones not in the table: world average (same source, 2025)
FALLBACK_GLOBAL_INTENSITY = 458.0

# Old zone codes that Electricity Maps does not accept
_ZONE_ALIASES = {
    "US-MIDA": "US-MIDA-PJM",
    "US-CAL": "US-CAL-CISO",
    "US-NY": "US-NY-NYIS",
    "US-TEX": "US-TEX-ERCO",
    "CL": "CL-SEN",
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
    "CA": "CA",
    "US": "US",
    "LT": "LT",
    "LV": "LV",
    "EE": "EE",
    "SI": "SI",
    "CL": "CL-SEN",
    "PH": "PH",
    "VN": "VN",
    "EG": "EG",
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

# IANA time zone -> country, used to guess the zone without network access
_TIMEZONE_TO_COUNTRY = {
    "Europe/Warsaw": "PL",
    "Europe/Berlin": "DE",
    "Europe/Paris": "FR",
    "Europe/London": "GB",
    "Europe/Stockholm": "SE",
    "Europe/Oslo": "NO",
    "Europe/Madrid": "ES",
    "Europe/Rome": "IT",
    "Europe/Copenhagen": "DK",
    "Europe/Amsterdam": "NL",
    "Europe/Zurich": "CH",
    "Europe/Vienna": "AT",
    "Europe/Prague": "CZ",
    "Europe/Helsinki": "FI",
    "Europe/Lisbon": "PT",
    "Europe/Brussels": "BE",
    "Europe/Dublin": "IE",
    "Europe/Bucharest": "RO",
    "Europe/Budapest": "HU",
    "Europe/Bratislava": "SK",
    "Europe/Zagreb": "HR",
    "Europe/Sofia": "BG",
    "Europe/Athens": "GR",
    "Europe/Kiev": "UA",
    "Europe/Kyiv": "UA",
    "Europe/Istanbul": "TR",
    "Europe/Vilnius": "LT",
    "Europe/Riga": "LV",
    "Europe/Tallinn": "EE",
    "Europe/Ljubljana": "SI",
    "Asia/Tokyo": "JP",
    "Asia/Shanghai": "CN",
    "Asia/Kolkata": "IN",
    "Asia/Seoul": "KR",
    "Asia/Taipei": "TW",
    "Asia/Singapore": "SG",
    "Asia/Bangkok": "TH",
    "Asia/Kuala_Lumpur": "MY",
    "Asia/Jakarta": "ID",
    "Asia/Manila": "PH",
    "Asia/Ho_Chi_Minh": "VN",
    "Asia/Dubai": "AE",
    "Asia/Riyadh": "SA",
    "Asia/Jerusalem": "IL",
    "Africa/Cairo": "EG",
    "Africa/Johannesburg": "ZA",
    "Pacific/Auckland": "NZ",
    "Australia/Melbourne": "AU",
    "Australia/Sydney": "AU",
    "America/Sao_Paulo": "BR",
    "America/Mexico_City": "MX",
    "America/Argentina/Buenos_Aires": "AR",
    "America/Santiago": "CL",
    "America/Toronto": "CA",
    "America/Vancouver": "CA",
    "America/New_York": "US",
    "America/Chicago": "US",
    "America/Denver": "US",
    "America/Los_Angeles": "US",
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

# Energy not attributed to a tracked app (OS, display, other processes)
OTHER_APP_NAME = "(other: system + untracked)"

# A longer gap between ticks (sleep, hibernate) counts as one interval
MAX_TICK_GAP_SEC = 60.0

# Upper bounds for TDPs reported by drivers; larger values are placeholders
CPU_TDP_MAX_WATTS = 500.0
GPU_TDP_MAX_WATTS_LAPTOP = 250.0
GPU_TDP_MAX_WATTS = 1500.0

# Shortest hourly bucket used as a forecast sample
MIN_FORECAST_BUCKET_SEC = 300.0

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

# ==========================================
# HPC / cluster (SLURM, PBS, LSF, SGE) estimation constants
# Methodology follows the Green Algorithms model (green-algorithms.org):
#   energy_kWh = time_h * (n_cores * P_core * u_core
#                          + n_gpus * P_gpu * u_gpu
#                          + mem_GB * P_mem) * PUE / 1000
# ==========================================

# Data-center Power Usage Effectiveness: a real facility draws more than the IT
# load for cooling, power delivery, etc. 1.0 = perfect, ~1.5-1.6 world average.
HPC_DEFAULT_PUE = 1.5

# Fallback per-core CPU power (W) when the CPU model / TDP is unknown. Server
# CPUs draw roughly 6-12 W per physical core at full load.
HPC_DEFAULT_WATTS_PER_CORE = 9.0

# Fallback per-accelerator power (W) when the GPU model is unknown but GPUs are
# allocated (typical data-center accelerator).
HPC_DEFAULT_GPU_WATTS = 300.0

# Memory power draw per allocated GB (Green Algorithms constant).
HPC_MEM_WATTS_PER_GB = 0.3725

# Default utilisation assumptions when real usage is unknown (0..1). HPC batch
# jobs are typically sized to run their cores/GPUs hot, so default to full load.
HPC_DEFAULT_CPU_UTILIZATION = 1.0
HPC_DEFAULT_GPU_UTILIZATION = 1.0

# How often the `hpc run` wrapper samples power while measuring (seconds).
HPC_SAMPLE_INTERVAL_SEC = 5.0

# Joules per kWh, for converting SLURM ``ConsumedEnergy`` (J) to kWh.
JOULES_PER_KWH = 3_600_000.0
