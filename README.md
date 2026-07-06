# Carbon Footprint Tracker

[![Version](https://img.shields.io/badge/version-1.1.5-brightgreen.svg)]()
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)


A cross-platform carbon footprint tracker that monitors your computer usage and calculates real-time CO2 emissions per application. Available as a **Python library**, **CLI tool**, **desktop GUI**, and **native C++ application**.

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Python Library Usage](#python-library-usage)
- [CLI Reference](#cli-reference)
- [HPC / Cluster Jobs (SLURM, PBS, LSF, SGE)](#hpc--cluster-jobs-slurm-pbs-lsf-sge)
- [GUI Application](#gui-application)
- [Project Files (.carbon.json)](#project-files-carbonjson)
- [C++ Application](#c-application)
- [How It Works](#how-it-works)
- [Computational Efficiency](#computational-efficiency)
- [Known Issues](#known-issues)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [FAQ](#faq)
- [License](#license)

---

## Features

- **Per-Process Tracking** - monitors CPU and GPU usage only for **selected processes**, not the entire system, keeping overhead minimal
- **Measured Power (not just estimates)** - reads *real* wattage where the hardware exposes it: whole-system draw from the **battery** (laptops on battery), **CPU package power** via Intel/AMD **RAPL** (Linux) or a **LibreHardwareMonitor**/OpenHardwareMonitor sensor (Windows), and **GPU power** via `nvidia-smi` or LibreHardwareMonitor. Falls back to a TDP estimate only for parts that can't be read - and **warns you** when it does.
- **Auto-Detect Hardware** - identifies your CPU/GPU and detects TDP **directly from the device** when possible (RAPL power limits, `nvidia-smi`/`rocm-smi`), otherwise looks it up from built-in tables covering Intel, AMD, NVIDIA (incl. laptop and RTX A-series workstation GPUs), and Apple Silicon. Detects laptop vs desktop and **WSL**.
- **Gaussian-Mixture Forecasting** - projects future carbon both for the whole system and **per application** using a dependency-free 1-D Gaussian Mixture model, capturing distinct usage modes with a 95% confidence range
- **Browser Tab Filtering** - filter energy tracking to specific browser tabs by keyword (e.g., only count YouTube in Firefox)
- **HPC / Cluster Jobs** - measure or estimate the footprint of batch jobs on **SLURM, PBS/Torque, LSF and SGE**. Reads the resources a job was allocated (nodes, cores, GPUs, memory), uses SLURM `sacct` energy accounting or RAPL/`nvidia-smi` when available, and otherwise emits a transparent **manual-computation worksheet** (time + hardware + formula) so the cost can be recomputed by hand.
- **Real-Time Carbon Intensity** - fetches live grid carbon intensity from the [Electricity Maps API](https://www.electricitymaps.com/) with 40+ zone fallbacks
- **Auto Country Detection** - detects your location via IP geolocation and maps it to the correct electricity zone
- **Auto Report on Stop** - when you stop monitoring (GUI or API), a JSON report is automatically saved with full session data
- **Project File Management** - save/load `.carbon.json` project files with full session history, app data, and file tracking
- **Future & Past Projections** - forecast future carbon costs or analyze historical sessions
- **Desktop GUI** - full-featured PyQt5 GUI with dark theme, dashboard, app selector, project management, and forecast tools
- **CLI Tool** - scriptable command-line interface for automation and CI/CD pipelines
- **Native C++ Core** - high-performance C++ application with CMake build system

> New here? See **[instruction.md](https://github.com/kugi8412/CarbonFootprint/blob/main/instruction.md)** for a short Windows / Linux / macOS / WSL start guide.

---

## Quick Start

### Option A - Install as Python Library (recommended)

```bash
pip install carbon-footprint-tracker
```

Then from Python:

```python
from carbon_tracker import CarbonTracker

tracker = CarbonTracker()
tracker.add_app("Code.exe")
tracker.add_app("firefox.exe")
tracker.start()

tracker.stop()
session = tracker.get_session_data()
print(session.summary())
```

### Option B - GUI Application

```bash
pip install carbon-footprint-tracker[gui]
carbon-tracker-gui
```

This opens a desktop application with tabs for:
- **Dashboard** - live CO2, energy, and per-app stats
- **Applications** - dynamically add/remove apps and browser tab filters
- **Projects & Files** - create projects, scan directories, select source files
- **Settings** - hardware config, zone, API key
- **History & Forecast** - view past sessions and project future carbon costs

### Option C - Build from C++ Source

```bash
git clone https://github.com/kugi8412/CarbonFootprint.git
cd CarbonFootprint

# Windows
build.bat
build\Release\carbon_tracker.exe

# Linux / macOS
chmod +x build.sh && ./build.sh
./build/carbon_tracker
```

**Prerequisites:**

| OS | Requirements | Install |
|----|-------------|---------|
| **Windows** | Visual Studio 2017+ (C++ workload) **or** MinGW-w64, CMake | [visualstudio.microsoft.com](https://visualstudio.microsoft.com/), [cmake.org](https://cmake.org/download/) |
| **Linux** | GCC 7+, CMake, X11 headers | `sudo apt install cmake build-essential libx11-dev` |
| **macOS** | Xcode CLI tools, CMake | `xcode-select --install && brew install cmake` |

> On Windows `build.bat` auto-detects an installed Visual Studio (via `vswhere`)
> or MinGW-w64 compiler, so it works from a normal PowerShell/cmd prompt - you no
> longer need the "Developer PowerShell for VS".

---

## Python Library Usage

### Basic Monitoring

```python
from carbon_tracker import CarbonTracker

tracker = CarbonTracker()
tracker.add_app("Code.exe")
tracker.add_app("chrome.exe")
tracker.start()

# Check status while running
snapshot = tracker.get_snapshot()
print(f"CO2: {snapshot['total_carbon_grams']:.2f} g")
print(f"Energy: {snapshot['total_energy_kwh']*1000:.4f} Wh")

# Add/remove apps dynamically
tracker.add_app("blender.exe")
tracker.remove_app("chrome.exe")

tracker.stop()
session = tracker.get_session_data()
print(session.summary())
```

### Browser Tab Filtering

```python
from carbon_tracker import CarbonTracker
from carbon_tracker.models import BrowserTabFilter

tracker = CarbonTracker()
tracker.add_app("firefox.exe")

# Only count energy when Firefox title contains "YouTube" or "Spotify"
tracker.add_tab_filter(BrowserTabFilter(
    browser="firefox.exe",
    keywords=["YouTube", "Spotify"]
))

tracker.start()
```

### Hardware Detection

```python
from carbon_tracker.hardware import detect_hardware

hw = detect_hardware()
print(f"CPU: {hw.cpu_name} ({hw.cpu_tdp_watts}W TDP)")
print(f"GPU: {hw.gpu_name} ({hw.gpu_tdp_watts}W TDP)")
print(f"Laptop: {hw.is_laptop}")
print(f"Cores: {hw.cpu_cores}")
```

### Auto Zone Detection

```python
from carbon_tracker.carbon_api import auto_detect_zone, fetch_carbon_intensity

zone = auto_detect_zone()
print(f"Detected zone: {zone}")  # e.g., "PL"

intensity = fetch_carbon_intensity(zone)
print(f"Grid intensity: {intensity} gCO2/kWh")
```

### Project Management

```python
from carbon_tracker import CarbonProject

# Create a new project
project = CarbonProject(name="My Web App", description="Frontend development")
project.zone = "DE"

# Scan a directory for source files
found = project.scan_directory("./src", extensions=[".py", ".js", ".tsx"])
print(f"Found {len(found)} source files")
project.add_files(found)

# Add a monitoring session
project.add_session(session)
project.save("my_project.carbon.json")

# Load later
loaded = CarbonProject.load("my_project.carbon.json")
print(f"Total CO2: {loaded.total_carbon_grams():.2f} g")
print(f"Total energy: {loaded.total_energy_kwh():.4f} kWh")

# Per-app breakdown across all sessions
for app, stats in loaded.per_app_totals().items():
    print(f"  {app}: {stats['total_carbon_grams']:.2f}g CO2, {stats['total_seconds']/3600:.1f}h")

# Project future carbon cost
projection = loaded.project_future(hours=8.0)
print(f"Projected 8h CO2: {projection['projected_carbon_grams']:.2f} g")
```

### Import Historical Sessions

```python
from carbon_tracker import CarbonProject
from carbon_tracker.models import SessionData

project = CarbonProject.load("my_project.carbon.json")

# Import a past session manually
past = SessionData(
    start_time="2025-01-15T09:00:00",
    duration_seconds=14400,  # 4 hours
    total_carbon_grams=45.0,
    total_energy_kwh=0.120,  # 120 Wh = 0.120 kWh
    zone="PL"
)
project.add_session(past)
project.save("my_project.carbon.json")

projection = project.project_future(hours=4.0)
print(f"4h forecast: {projection['projected_carbon_grams']:.2f} g CO2")
```

### Non-Electrical Activities (LLM / GPT Integration)

Track carbon emissions from non-computer sources - driving, flights, food, heating, or any custom activity. This API is designed for LLM models (GPT, Claude, etc.) to submit structured carbon data.

```python
from carbon_tracker import ActivityTracker, Activity

tracker = ActivityTracker()

# Add activities using factory methods
tracker.add(Activity.driving(km=25, vehicle="petrol_car"))
tracker.add(Activity.flight(km=800, flight_class="economy"))
tracker.add(Activity.food("beef", kg=0.3))
tracker.add(Activity.heating(kwh=50, fuel="natural_gas"))
tracker.add(Activity.custom("Cement production", co2_grams=5000))

# Get totals
print(f"Total CO2: {tracker.total_co2_grams():.1f} g")
print(f"Total CO2: {tracker.total_co2_kg():.3f} kg")

# Breakdown by category
for cat, co2 in tracker.by_category().items():
    print(f"  {cat}: {co2:.1f} g")

# Full report
print(tracker.report())

# Save / load
tracker.save("my_activities.json")
loaded = ActivityTracker.load("my_activities.json")
```

**Supported vehicle types:** `petrol_car`, `diesel_car`, `hybrid_car`, `electric_car`, `motorcycle`, `bus`, `train`, `tram`, `scooter_electric`, `bicycle`, `walking`

**Supported flight classes:** `economy`, `premium_economy`, `business`, `first`

**Supported food types:** `beef`, `lamb`, `pork`, `chicken`, `fish`, `cheese`, `milk`, `eggs`, `rice`, `bread`, `vegetables`, `fruit`, `tofu`, `nuts`, `coffee`

**Supported heating fuels:** `natural_gas`, `heating_oil`, `coal`, `wood_pellets`, `electricity`, `district_heating`

### Combining Computer + Activity Data in a Project

```python
from carbon_tracker import CarbonTracker, CarbonProject, Activity

# Track computer usage
tracker = CarbonTracker(apps=["Code.exe"])
tracker.start()
session = tracker.stop()

# Create project with both data sources
project = CarbonProject(name="Full Day Carbon")
project.add_session(session)
project.add_activity(Activity.driving(km=30, vehicle="petrol_car"))
project.add_activity(Activity.food("chicken", kg=0.5))
project.save("full_day.carbon.json")
print(project.summary())
```

### HPC / Cluster Jobs (Python API)

```python
from carbon_tracker import detect_hpc_job, build_hpc_report, run_and_measure

# Inside a batch job: read what the scheduler allocated
job = detect_hpc_job()          # None when not inside SLURM/PBS/LSF/SGE

# Measure a command and build a report
exit_code, elapsed, energy_kwh, source = run_and_measure(["python", "train.py"])
report = build_hpc_report(
    job=job,
    elapsed_seconds=elapsed,
    measured_energy_kwh=energy_kwh,
    measured_source=source,
    zone="FR",
)
print(report.summary())
print(report.manual_computation_report())
report.save("job.carbon.json")
```

---

## CLI Reference

### Detect Hardware & Location

```bash
carbon-tracker detect
```

Output:
```
=== Hardware Detection ===
  CPU: AMD Ryzen 7 5800X (8 cores)
  CPU TDP: 105 W
  GPU: NVIDIA GeForce RTX 3070
  GPU TDP: 220 W
  Laptop: No

=== Location Detection ===
  Detected Zone: PL
  Carbon Intensity: 680 gCO2/kWh (fallback)
```

### Start Monitoring

```bash
# Monitor specific apps with auto-detected zone
carbon-tracker monitor --app Code.exe --app firefox.exe

# Specify zone and save to project
carbon-tracker monitor --app Code.exe --zone DE --project my_project.carbon.json

# Custom update interval (seconds)
carbon-tracker monitor --app blender.exe --interval 5
```

### Project Management

```bash
# Create a new project
carbon-tracker project create my_project.carbon.json --name "Web App" --zone PL

# View project info
carbon-tracker project info my_project.carbon.json

# Forecast future carbon cost
carbon-tracker project forecast my_project.carbon.json --hours 8

# Add a manual session
carbon-tracker project add-session my_project.carbon.json \
    --duration 3600 --carbon 12.5 --energy 35.0
```

### HPC / Cluster Jobs (SLURM, PBS, LSF, SGE)

On a shared compute cluster a workload is submitted through a batch scheduler
(`sbatch`, `qsub`, `bsub`). There is usually no battery and no per-app foreground
window to track, so `carbon-tracker` instead reads the resources the job was
**allocated** and reports the footprint. When the node exposes no power sensor
and SLURM energy accounting is unavailable, it falls back to an estimate and
always prints a transparent **manual-computation worksheet** recording how long
the job ran and on exactly what hardware, so the cost can be recomputed by hand
with your site's real numbers.

```bash
# Show what the scheduler allocated to the current job
carbon-tracker hpc detect

# Wrap and MEASURE a command inside a batch script (best accuracy).
# Place the command after `--`. Measures wall time + RAPL/nvidia-smi power.
carbon-tracker hpc run --output $SLURM_JOB_ID.carbon.json -- python train.py

# Report for the current job (uses SLURM `sacct` ConsumedEnergy when available)
carbon-tracker hpc report --zone FR

# Report for a finished SLURM job by id (queries sacct)
carbon-tracker hpc report --job-id 123456 --zone DE

# Estimate without a scheduler: specify resources and wall time by hand
carbon-tracker hpc report --cpus 64 --gpus 4 --nodes 2 --mem-gb 256 \
    --elapsed 7200 --zone PL --pue 1.6 --output run.carbon.json
```

Inside a `sbatch` script:

```bash
#!/bin/bash
#SBATCH --job-name=train
#SBATCH --nodes=1 --ntasks=1 --cpus-per-task=16 --gpus=2 --mem=64G --time=04:00:00

carbon-tracker hpc run --output ${SLURM_JOB_ID}.carbon.json -- \
    python train.py --epochs 50
```

Useful flags: `--pue` (datacentre Power Usage Effectiveness, default `1.5`),
`--cpu-util` / `--gpu-util` (assumed utilisation `0..1`), `--no-sacct` (skip the
SLURM accounting lookup), `--elapsed` (wall-clock seconds when not measured).

Energy precedence: power sampled while wrapping the command (`hpc run`) →
SLURM `sacct` `ConsumedEnergy` → resource-based estimate (Green-Algorithms
model: per-core + per-GPU + per-GB power × PUE).

---

## GUI Application

Launch the GUI:

```bash
carbon-tracker-gui
# or
python -m carbon_tracker.gui
```

### Dashboard Tab

Live-updating display showing:
- Total CO2 emissions (grams)
- Total energy consumed (Wh)
- Session duration
- Current grid carbon intensity
- Per-application breakdown table (app name, active time, energy, CO2, CPU%)

Use the **Start** / **Stop** buttons to control monitoring.

### Applications Tab

- **Add App** - type an application name (e.g., `Code.exe`) to add it
- **Pick Running** - opens a dialog listing all running processes; click to select
- **Remove** - remove selected app from monitoring (data is preserved)
- **Tab Filters** - add browser + keyword pairs to filter energy to specific tabs

### Project & Files Tab

- **New Project** - create a `.carbon.json` project with name and description
- **Open Project** - load an existing project file
- **Save Project** - save current state  
- **Add Files** - pick individual files to associate with the project
- **Scan Directory** - scan a folder for source files by extension (`.py`, `.js`, `.cpp`, etc.)
- **File List** - view and manage project files with select/deselect all

### Settings Tab

- Override auto-detected CPU/GPU TDP values
- Set electricity zone manually
- Enter Electricity Maps API key for live data
- Adjust monitoring update interval

### History & Forecast Tab

- View all recorded sessions with timestamp, duration, CO2, and energy
- **Import Session** - add historical data from past work
- **Forecast** - predict future carbon cost for N hours based on all session data

---

## Project Files (.carbon.json)

Project files store everything needed to track and forecast carbon costs:

```json
{
  "id": "a1b2c3d4-...",
  "name": "My Web App",
  "description": "Frontend development project",
  "created": "2025-06-15T10:00:00",
  "zone": "PL",
  "sessions": [
    {
      "start_time": "2025-06-15T10:00:00",
      "duration_seconds": 7200,
      "total_carbon_grams": 25.4,
      "total_energy_kwh": 0.0682,
      "zone": "PL",
      "apps": { "Code.exe": { "active_seconds": 6800, "carbon_grams": 18.1 } }
    }
  ],
  "files": ["src/app.py", "src/utils.py"],
  "tags": ["python", "web"]
}
```

**Use cases:**
- Track carbon cost of a specific software project over weeks/months
- Compare energy profiles of different tools (VS Code vs. JetBrains, Chrome vs. Firefox)
- Generate forecasts: "If I work 8h/day for 2 weeks, how much CO2?"
- Import past sessions to build a complete carbon history

---

## C++ Application

The native C++ application provides the same core functionality with lower overhead.

### Interactive Mode

```bash
./carbon_tracker        # Linux/Mac
carbon_tracker.exe      # Windows
```

Menu options:
```
=== SETUP MENU ===
  1.  List running processes
  2.  Add application to monitor
  3.  Remove application from monitor
  4.  Show monitored applications
  5.  Set region/zone for carbon intensity
  6.  Configure system parameters
  7.  Import previous session data
  8.  Show current carbon intensity
  9.  START monitoring
  10. Auto-detect hardware
  11. Auto-detect zone from IP
  0.  Exit
```

### Live Commands (during monitoring)

| Command | Description |
|---------|-------------|
| `add <app>` | Start tracking a new application |
| `remove <app>` | Stop tracking (data preserved in report) |
| `list` | Show active and removed applications |
| `status` | Current CO2, energy, and per-app stats |
| `project <hours>` | Predict future CO2 for N hours |
| `import` | Import a previous session |
| `stop` / `quit` | Stop and generate report |

### Build Flags

```bash
cmake .. -DUSE_NVML=ON    # NVIDIA GPU monitoring (requires NVML)
cmake .. -DUSE_CURL=ON    # libcurl for HTTP (alternative to WinHTTP)
```

---

## How It Works

### Power Model

The tracker prefers **measured** power and only estimates what the hardware
won't report. It picks the best available source in this order:

1. **Battery discharge (whole system)** - while a laptop runs on battery, the
   discharge rate *is* the real total wattage (CPU + GPU + screen + everything).
   This is the gold standard, used directly with no heuristics.
2. **Component sum (on AC)** - when plugged in, the battery reports no draw, so
   the total is assembled from per-component sensors:
   - **CPU package power** - Intel/AMD RAPL (Linux) or a LibreHardwareMonitor /
     OpenHardwareMonitor sensor (Windows, via WMI or its `/data.json` web server).
   - **GPU power** - `nvidia-smi power.draw`, or LibreHardwareMonitor for
     AMD/Intel GPUs.
   - **System base** - a small fixed offset for display, RAM, storage, fans.
3. **TDP estimate (fallback)** - for any component without a sensor, power is
   estimated from its TDP and CPU utilization with a single non-linear curve.
   The app **flags the result as estimated** and tells you how to enable real
   measurement (see [instruction.md](https://github.com/kugi8412/CarbonFootprint/blob/main/instruction.md)).

Each app's share is proportional to its CPU usage, with an active-window bonus
for the foreground app. The reported `power_source` shows exactly what was
measured, e.g. `battery`, `components(cpu:meas,gpu:meas)`, or `estimate`.

### Forecasting (Gaussian Mixture)

Future carbon is projected with a dependency-free 1-D **Gaussian Mixture model**
fit on per-hour usage samples - for the whole system and for **each application**
separately. This captures multiple usage modes (e.g. idle vs. heavy compile)
rather than a single average, and reports a 95% confidence interval.

### Carbon Calculation

$$CO_2 = \text{Energy (kWh)} \times \text{Grid Intensity (gCO}_2\text{/kWh)}$$

Grid intensity comes from:
1. **Live API** - Electricity Maps (requires free API key for best results)
2. **Fallback Table** - 40+ built-in zones with day/night intensity values

### Zone Detection

1. Query `ipapi.co` → get country code
2. Fallback to `ip-api.com` if first fails
3. Map country code to electricity zone (e.g., `US` → `US-MIDA-PJM`)
4. Fetch carbon intensity for that zone

---

## Computational Efficiency

The tracker is designed to be **lightweight in both time and memory**:

- **Per-process monitoring only** - CPU and GPU usage is measured only for the processes you explicitly select, not system-wide. This avoids unnecessary overhead from iterating all running processes for full metrics.
- **Low memory footprint** - per-app data is stored as simple counters (avg CPU, peak CPU, energy sum, carbon sum, hourly buckets). No raw timeseries or sample buffers are kept in memory.
- **Configurable interval** - the default 2-second monitoring interval keeps CPU overhead under 1%. You can increase it (e.g., 5s or 10s) for even lower overhead.
- **Proportional energy allocation** - instead of reading hardware power sensors (which requires elevated privileges and polling overhead), the tracker estimates each app's energy share from its CPU percentage relative to total system usage. This uses only `psutil.process_iter()` with minimal fields.
- **Background API calls** - carbon intensity is fetched from the Electricity Maps API in a separate thread every 15 minutes, so network latency never blocks the monitoring loop.
- **No disk I/O during monitoring** - data is accumulated in memory and only written to disk when you stop monitoring or save a project.

---

## Known Issues

### GPU Auto-Detection

GPU auto-detection may fail or return the integrated GPU (e.g., Intel UHD) instead of the discrete GPU (e.g., NVIDIA RTX) on some systems. This happens because:

- On Windows, the registry enumeration in `detect_gpu_name()` iterates display adapter subkeys sequentially. The integrated GPU often appears first (subkey `0000`), and the discrete GPU appears later.
- The current logic skips entries containing "Intel" or "UHD" and picks the first non-Intel GPU, but on some systems with driver configurations the discrete GPU subkey may not have `DriverDesc` populated.
- On laptops with NVIDIA Optimus or AMD Switchable Graphics, the discrete GPU may not be visible in the registry when it is powered down.

**Workaround:** Manually set the GPU name and TDP in the Settings tab of the GUI, or pass a `HardwareInfo` object with the correct values when using the Python API:

```python
from carbon_tracker import CarbonTracker
from carbon_tracker.models import HardwareInfo

hw = HardwareInfo(
    gpu_name="NVIDIA GeForce RTX 3070",
    gpu_tdp_watts=220,
)
tracker = CarbonTracker(hardware=hw)
```

---

## Configuration

### Electricity Maps API Key (optional but recommended)

Get a free API key at [https://www.electricitymaps.com/free-tier-api](https://www.electricitymaps.com/free-tier-api).

**Python:**
```python
tracker = CarbonTracker(api_key="your-key-here")
```

**CLI:**
```bash
carbon-tracker monitor --app Code.exe --api-key YOUR_KEY
```

**GUI:** Enter in Settings tab.

### Supported Zones

| Zone | Region | Typical Intensity |
|------|--------|-------------------|
| `PL` | Poland | 700 gCO2/kWh |
| `DE` | Germany | 400 gCO2/kWh |
| `FR` | France | 70 gCO2/kWh |
| `SE` | Sweden | 30 gCO2/kWh |
| `GB` | United Kingdom | 250 gCO2/kWh |
| `US-CAL-CISO` | California | 230 gCO2/kWh |
| `US-MIDA-PJM` | Mid-Atlantic US | 400 gCO2/kWh |
| `US-TEX-ERCO` | Texas | 450 gCO2/kWh |
| `JP` | Japan | 500 gCO2/kWh |
| `AU` | Australia | 600 gCO2/kWh |
| `IN` | India | 700 gCO2/kWh |
| `BR` | Brazil | 80 gCO2/kWh |

Full list: 40+ zones in `carbon_tracker/carbon_api.py`.

---

## Project Structure

```
CarbonFootprint/
├── pyproject.toml              # Python package config (pip install)
├── MANIFEST.in                 # Package file inclusion rules
├── LICENSE                     # MIT License
├── README.md                   # This file
├── instruction.md              # Quick start (Windows/Linux/macOS/WSL)
├── PUBLISHING.md               # How to publish the package to PyPI
├── CMakeLists.txt              # C++ build config
├── build.bat                   # Windows C++ build script
├── build.sh                    # Linux/Mac C++ build script
│
├── carbon_tracker/             # Python package
│   ├── __init__.py             # Package entry point, exports
│   ├── _version.py             # Single source of truth for the version
│   ├── models.py               # Data models (HardwareInfo, SessionData, etc.)
│   ├── globals.py              # Constants, TDP tables, config
│   ├── hardware.py             # Auto-detect CPU/GPU + device/TDP lookup + WSL
│   ├── power.py                # Measured power (battery, RAPL, nvidia-smi, LHM)
│   ├── forecast.py             # Gaussian-Mixture forecasting (overall + per-app)
│   ├── carbon_api.py           # Carbon intensity API + zone detection
│   ├── activities.py           # Non-electrical activities API
│   ├── tracker.py              # Core monitoring engine (psutil-based)
│   ├── project.py              # Project file management (.carbon.json)
│   ├── cli.py                  # CLI entry point (argparse)
│   └── gui.py                  # Desktop GUI (PyQt5)
│
├── include/                    # C++ headers
│   ├── carbon_api.h
│   ├── carbon_engine.h
│   ├── daemon.h
│   ├── hardware_detect.h
│   ├── platform.h
│   ├── power_monitor.h
│   ├── process_monitor.h
│   ├── report.h
│   └── screen_monitor.h
│
├── src/                        # C++ source files
│   ├── main.cpp
│   ├── carbon_api.cpp
│   ├── carbon_engine.cpp
│   ├── daemon.cpp
│   ├── hardware_detect.cpp
│   ├── power_monitor.cpp
│   ├── process_monitor.cpp
│   ├── report.cpp
│   └── screen_monitor.cpp
│
└── build/                      # C++ build output (generated)
    └── Release/
        └── carbon_tracker.exe
```

---

## API Reference

### `CarbonTracker`

```python
from carbon_tracker import CarbonTracker

tracker = CarbonTracker(
    zone="PL",              # Electricity zone (auto-detected if omitted)
    api_key="",             # Electricity Maps API key
    update_interval=2.0,    # Monitoring interval in seconds
    hardware=None           # HardwareInfo (auto-detected if omitted)
)
```

| Method | Description |
|--------|-------------|
| `start()` | Begin monitoring in background threads |
| `stop()` → `SessionData` | Stop monitoring, return session data |
| `add_app(name)` | Add an application to monitor |
| `remove_app(name)` | Remove app (data preserved) |
| `add_tab_filter(filter)` | Add browser tab keyword filter |
| `get_snapshot()` → `dict` | Get current live stats |
| `get_session_data()` → `SessionData` | Get finalized session data |
| `project_future(hours)` → `ProjectionResult` | Forecast future emissions |

### `CarbonProject`

```python
from carbon_tracker import CarbonProject

project = CarbonProject(name="My App", description="...", zone="DE")
```

| Method | Description |
|--------|-------------|
| `save(path)` | Save project to `.carbon.json` |
| `CarbonProject.load(path)` → `CarbonProject` | Load from file |
| `add_session(session)` | Add a SessionData to history |
| `remove_session(session_id)` | Remove session by session ID |
| `scan_directory(path, extensions)` → `list` | Find source files |
| `add_files(paths)` | Associate files with project |
| `remove_files(paths)` | Remove file associations |
| `total_carbon_grams()` → `float` | Sum CO2 across sessions + activities |
| `total_energy_kwh()` → `float` | Sum energy across all sessions |
| `total_duration_hours()` → `float` | Sum time across all sessions |
| `per_app_totals()` → `dict` | Per-app aggregate stats |
| `project_future(hours)` → `dict` | Forecast from history |
| `add_activity(activity)` | Add a non-electrical Activity |
| `remove_activity(index)` | Remove activity by index |
| `activities_co2_grams()` → `float` | CO2 from activities only |
| `summary()` → `str` | Formatted text report |

### `ActivityTracker`

```python
from carbon_tracker import ActivityTracker, Activity

tracker = ActivityTracker()
tracker.add(Activity.driving(km=25))
tracker.add(Activity.flight(km=800, flight_class="economy"))
tracker.add(Activity.food("beef", kg=0.3))
tracker.add(Activity.heating(kwh=50, fuel="natural_gas"))
tracker.add(Activity.custom("My activity", co2_grams=100))
```

| Method | Description |
|--------|-------------|
| `add(activity)` | Add an Activity |
| `add_driving(km, vehicle, desc)` | Shortcut for driving |
| `add_flight(km, flight_class, desc)` | Shortcut for flight |
| `add_food(food_type, kg, desc)` | Shortcut for food |
| `add_heating(kwh, fuel, desc)` | Shortcut for heating |
| `add_custom(name, co2_grams, desc)` | Shortcut for custom |
| `total_co2_grams()` → `float` | Total CO2 (grams) |
| `total_co2_kg()` → `float` | Total CO2 (kg) |
| `by_category()` → `dict` | CO2 grouped by category |
| `equivalences()` → `dict` | Real-world equivalences |
| `report()` → `str` | Full text report |
| `save(path)` | Save to JSON |
| `ActivityTracker.load(path)` | Load from JSON |
| `to_dict_list()` → `list` | Export for LLM/API |
| `ActivityTracker.from_dict_list(items)` | Import from LLM/API |

### `Activity` Factory Methods

| Method | Args | Description |
|--------|------|-------------|
| `Activity.driving(km, vehicle)` | km, vehicle type | Driving emissions |
| `Activity.flight(km, flight_class)` | km, class | Flight emissions |
| `Activity.food(food_type, kg)` | type, weight | Food production emissions |
| `Activity.heating(kwh, fuel)` | energy, fuel type | Heating/energy emissions |
| `Activity.custom(name, co2_grams)` | name, grams | Any custom source |

### `SessionData`

```python
from carbon_tracker.models import SessionData

session = SessionData(
    start_time="2025-06-15T10:00:00",
    duration_seconds=7200,
    total_carbon_grams=25.4,
    total_energy_kwh=0.0682,
    zone="PL",
    apps={}
)
```

| Method | Description |
|--------|-------------|
| `summary()` → `str` | Human-readable session report |
| `to_dict()` → `dict` | Serialize to dictionary |
| `SessionData.from_dict(d)` | Deserialize from dictionary |

### `HardwareInfo`

```python
from carbon_tracker.models import HardwareInfo

hw = HardwareInfo(
    cpu_name="AMD Ryzen 7 5800X",
    cpu_cores=8,
    cpu_tdp_watts=105,
    gpu_name="NVIDIA GeForce RTX 3070",
    gpu_tdp_watts=220,
    is_laptop=False
)
```

### Utility Functions

```python
from carbon_tracker.hardware import detect_hardware
from carbon_tracker.carbon_api import auto_detect_zone, fetch_carbon_intensity

hw = detect_hardware()                    # HardwareInfo
zone = auto_detect_zone()                 # "PL"
intensity = fetch_carbon_intensity(zone)  # 680.0 (gCO2/kWh)
```

---

## FAQ

**Q: Do I need an API key?**  
A: No. The tracker has built-in fallback intensity values for 40+ zones. An API key gives you live real-time data from Electricity Maps.

**Q: Does it work on Linux/macOS?**  
A: Yes. Hardware detection, process monitoring, and active window detection all have cross-platform implementations.

**Q: How accurate is the power estimation?**  
A: It depends on the source. On battery, or on AC with CPU/GPU sensors available
(RAPL on Linux, LibreHardwareMonitor on Windows, `nvidia-smi`), power is
**measured** and accurate to within a few percent. When a component has no
sensor, it falls back to a TDP-based estimate (typically +/- 30%) and the app
**warns you** that the value is estimated.

**Q: I'm on AC power - why does it say "estimated"?**  
A: A plugged-in battery reports no discharge, so whole-system wattage can't be
read from it. The tracker then measures each component it can (GPU via
`nvidia-smi`, CPU via RAPL/LibreHardwareMonitor) and estimates the rest. To get
real CPU power on Windows, run **LibreHardwareMonitor**; on Linux RAPL works out
of the box. See [instruction.md](https://github.com/kugi8412/CarbonFootprint/blob/main/instruction.md).

**Q: Can I track GPU-heavy workloads?**  
A: The tracker includes GPU TDP in calculations. For NVIDIA GPUs, the C++ version can use NVML for real power readings.

**Q: What's the difference between the Python and C++ versions?**  
A: The Python version is easier to install (`pip install`) and has the GUI. The C++ version has lower overhead and direct hardware access (RAPL, NVML).


---

## License

MIT License - see [LICENSE](https://github.com/kugi8412/CarbonFootprint/blob/main/LICENSE) for details.
