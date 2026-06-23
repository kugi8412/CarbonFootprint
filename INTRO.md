# Getting Started

A short guide to install and run **Carbon Footprint Tracker** on Windows, Linux,
macOS, and WSL.

---

## 1. Requirements

- **Python 3.8+** (the package). Check with `python --version` (or `py -3 --version` on Windows).
- Optional: **PyQt5** for the desktop GUI.
- Optional (for *measured* CPU/GPU power instead of estimates): see [section 5](#5-get-real-measured-power-optional).

> On Windows, if `python` points to an old version, use `py -3` everywhere below.

---

## 2. Install (all platforms)

```bash
# Core library + CLI
pip install carbon-footprint-tracker

# With the desktop GUI
pip install "carbon-footprint-tracker[gui]"
```

Or from a local clone:

```bash
git clone https://github.com/kugi8412/CarbonFootprint.git
cd CarbonFootprint
pip install -e ".[gui]"
```

---

## 3. Run

### Check your hardware detection first

```bash
carbon-tracker detect          # or: py -3 -m carbon_tracker.cli detect
```

You should see your CPU/GPU, detected TDP, and whether power will be **measured**
or **estimated**.

### CLI monitoring

```bash
carbon-tracker monitor --app Code.exe --app firefox
```

Press `Ctrl+C` to stop; a JSON report is written automatically.

### GUI

```bash
carbon-tracker-gui             # or: py -3 -m carbon_tracker.gui
```

---

## 4. Platform notes

### Windows

```powershell
py -3 -m pip install "carbon-footprint-tracker[gui]"
carbon-tracker detect
```

- **Battery laptops:** unplug the charger to get the *real* whole-system wattage
  from the battery. On AC the battery can't report draw (see section 5).
- **NVIDIA GPUs:** real GPU power is read automatically via `nvidia-smi` (make
  sure it is on your `PATH`, normally installed with the driver).

### Linux

```bash
sudo apt install python3-pip           # if needed
pip install "carbon-footprint-tracker[gui]"
carbon-tracker detect
```

- Best case: real CPU power is read from **Intel/AMD RAPL** automatically
  (`/sys/class/powercap`) — **no extra tools, works on AC**.
- If RAPL is permission-restricted: `sudo chmod -R a+r /sys/class/powercap/intel-rapl*`.
- GUI needs X11/Wayland; for headless use the CLI.

### macOS

```bash
pip3 install "carbon-footprint-tracker[gui]"
carbon-tracker detect
```

- On battery, whole-system power is read from `ioreg` (AppleSmartBattery).
- On AC, power falls back to a TDP estimate (Apple does not expose a simple
  package-power counter without extra tools).

### WSL (Windows Subsystem for Linux)

```bash
pip install carbon-footprint-tracker
carbon-tracker detect
```

- WSL is auto-detected. Battery/AC state is read from the **Windows host** via
  `powershell.exe`, so it works inside WSL.
- Tracked apps running on the **Windows host** (e.g. `chrome.exe`, `Code.exe`)
  are detected from WSL and their **real CPU%** is measured by sampling Windows
  process CPU time via `powershell.exe`; this also provides the Windows-host
  system CPU used to allocate per-app energy.
- WSL has no `/sys/class/powercap`, so CPU RAPL is **not** available there; run
  natively on Linux for RAPL, or use LibreHardwareMonitor on the Windows side.

---

## 5. Get real, measured power (optional)

By default, power is **measured** when a source is available and otherwise
**estimated** (the app warns you which). To maximize measured coverage:

| Platform | What you get out of the box | How to measure the **CPU** on AC |
|----------|-----------------------------|----------------------------------|
| **Linux (native)** | CPU via RAPL + GPU via nvidia-smi | already measured — nothing to do |
| **Windows** | GPU via nvidia-smi | run **LibreHardwareMonitor** (see below) |
| **macOS** | whole-system on battery only | run on battery, or use a sensor tool |
| **WSL** | battery state from host | use LibreHardwareMonitor on Windows |

### LibreHardwareMonitor (Windows CPU power on AC)

1. Download and run **LibreHardwareMonitor** (free) **as Administrator**.
2. Either keep it running (its WMI sensor provider is read automatically), **or**
   enable **Options → Remote Web Server → Run** (default port `8085`).
3. Re-check:

   ```powershell
   py -3 -c "from carbon_tracker.power import read_cpu_power_watts; print(read_cpu_power_watts())"
   ```

   A result like `(22.8, 'lhm-http')` or `(22.8, 'sensor')` means CPU power is now
   measured. The tracker then reports `components(cpu:meas,gpu:meas)`.

Host/port are configurable in `carbon_tracker/globals.py`
(`LHM_HTTP_HOST`, `LHM_HTTP_PORT`).

---

## 6. C++ application (optional, low overhead)

```bash
# Windows
build.bat
build\Release\carbon_tracker.exe

# Linux / macOS
chmod +x build.sh && ./build.sh
./build/carbon_tracker
```

Prerequisites: a C++17 compiler and CMake. The C++ core auto-detects hardware
the same way (RAPL on Linux, `nvidia-smi`/`rocm-smi` for GPUs).

---

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `python` runs Python 2 | use `py -3` (Windows) or `python3` (Linux/macOS) |
| `detect` shows **estimated** power on a laptop | you're on AC — unplug, or set up a sensor (section 5) |
| CPU power is `None` on Windows | LibreHardwareMonitor not running / not elevated |
| GPU power is `None` | non-NVIDIA GPU without nvidia-smi — use LibreHardwareMonitor |
| GUI won't start | install the GUI extra: `pip install "carbon-footprint-tracker[gui]"` |
