#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI entry point for carbon-tracker.
"""

import time
import argparse

from carbon_tracker import CarbonTracker, CarbonProject


def main():
    parser = argparse.ArgumentParser(
        prog="carbon-tracker",
        description="Carbon Footprint Tracker - Monitor your computer's carbon emissions",
    )
    sub = parser.add_subparsers(dest="command")

    # Monitor
    mon = sub.add_parser("monitor", help="Start monitoring carbon footprint")
    mon.add_argument(
        "--app", action="append", default=[], help="App to monitor (repeatable)"
    )
    mon.add_argument(
        "--zone", default=None, help="Electricity zone (e.g., PL, DE, US-CAL)"
    )
    mon.add_argument("--api-key", default="", help="Electricity Maps API key")
    mon.add_argument(
        "--interval", type=float, default=2.0, help="Update interval in seconds"
    )
    mon.add_argument(
        "--project", default=None, help="Save results to project file (.carbon.json)"
    )

    # Project
    proj = sub.add_parser("project", help="Manage carbon footprint projects")
    proj.add_argument("action", choices=["create", "info", "add-session", "forecast"])
    proj.add_argument("file", help="Project file (.carbon.json)")
    proj.add_argument("--name", default="My Project", help="Project name (for create)")
    proj.add_argument("--hours", type=float, default=8.0, help="Hours to forecast")

    _ = sub.add_parser("detect", help="Auto-detect hardware and location")

    args = parser.parse_args()

    if args.command == "monitor":
        _cmd_monitor(args)
    elif args.command == "project":
        _cmd_project(args)
    elif args.command == "detect":
        _cmd_detect()
    else:
        parser.print_help()


def _cmd_monitor(args):
    if not args.app:
        print("No apps specified. Use --app <name> to add apps to monitor.")
        print("Example: carbon-tracker monitor --app firefox.exe --app code.exe")
        return

    tracker = CarbonTracker(
        apps=args.app,
        zone=args.zone,
        api_key=args.api_key,
        update_interval=args.interval,
    )

    print(f"Carbon Footprint Tracker")
    print(f"  Zone:     {tracker.zone}")
    print(
        f"  CPU:      {tracker.hardware.cpu_name} ({tracker.hardware.cpu_tdp_watts}W)"
    )
    print(
        f"  GPU:      {tracker.hardware.gpu_name or 'Integrated'} ({tracker.hardware.gpu_tdp_watts}W)"
    )
    print(f"  Type:     {'Laptop' if tracker.hardware.is_laptop else 'Desktop'}")
    print(f"  Apps:     {', '.join(args.app)}")
    print(f"\nStarting... Press Ctrl+C to stop.\n")

    tracker.start()

    try:
        while True:
            time.sleep(5)
            snap = tracker.get_snapshot()
            elapsed = snap["total_seconds"]
            h, m, s = (
                int(elapsed) // 3600,
                (int(elapsed) % 3600) // 60,
                int(elapsed) % 60,
            )
            print(
                f"\r  {h}h{m:02d}m{s:02d}s | "
                f"CO2: {snap['total_carbon_grams']:.3f}g | "
                f"Energy: {snap['total_energy_kwh'] * 1000:.4f}Wh | "
                f"Grid: {snap['intensity']:.0f} gCO2/kWh"
                f"{'*' if snap['intensity_real'] else ''}    ",
                end="",
                flush=True,
            )
    except KeyboardInterrupt:
        print("\n\nStopping...")

    session = tracker.stop()
    print(f"\n{session.summary()}")

    if args.project:
        try:
            proj = CarbonProject.load(args.project)
        except FileNotFoundError:
            proj = CarbonProject(name=args.project.replace(".carbon.json", ""))
        proj.add_session(session)
        proj.save(args.project)
        print(f"\nSession saved to {args.project}")


def _cmd_project(args):
    if args.action == "create":
        proj = CarbonProject(name=args.name)
        proj.save(args.file)
        print(f"Created project: {args.file}")

    elif args.action == "info":
        proj = CarbonProject.load(args.file)
        print(proj.summary())

    elif args.action == "forecast":
        proj = CarbonProject.load(args.file)
        result = proj.project_future(args.hours)
        print(f"Forecast for {result['projected_hours']:.1f} hours:")
        print(f"  Projected CO2:    {result['projected_carbon_grams']:.2f} g")
        print(f"  Projected Energy: {result['projected_energy_kwh'] * 1000:.2f} Wh")
        print(f"  Rate:             {result['rate_grams_per_hour']:.2f} gCO2/hour")
        print(
            f"  Based on:         {result['based_on_sessions']} sessions ({result['based_on_hours']:.1f}h)"
        )


def _cmd_detect():
    from carbon_tracker.hardware import detect_hardware
    from carbon_tracker.carbon_api import auto_detect_zone, fetch_carbon_intensity

    print("<== Hardware Detection ==>")
    hw = detect_hardware()
    print(
        f"  CPU:  {hw.cpu_name or '(unknown)'} ({hw.cpu_tdp_watts}W, {hw.cpu_cores} cores)"
    )
    print(f"  GPU:  {hw.gpu_name or '(unknown)'} ({hw.gpu_tdp_watts}W)")
    print(f"  Type: {'Laptop' if hw.is_laptop else 'Desktop'}")
    print(f"  Base: {hw.base_system_watts}W")

    print("\n<== Location Detection ==>")
    zone, desc = auto_detect_zone()
    if zone:
        print(f"  Location: {desc}")
        print(f"  Zone:     {zone}")
        intensity, real = fetch_carbon_intensity(zone)
        print(
            f"  Intensity: {intensity:.0f} gCO2/kWh {'(live)' if real else '(estimate)'}"
        )
    else:
        print("  Could not auto-detect location.")


if __name__ == "__main__":
    main()
