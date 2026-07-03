#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI entry point for carbon-tracker.
"""

import time
import argparse
import sys

from carbon_tracker import CarbonTracker, CarbonProject
from carbon_tracker._version import __version__


def main():
    parser = argparse.ArgumentParser(
        prog="carbon-tracker",
        description="Carbon Footprint Tracker - Monitor your computer's carbon emissions",
    )
    parser.add_argument(
        "--version", action="version", version=f"carbon-tracker {__version__}"
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

    # HPC / cluster (SLURM, PBS, LSF, SGE)
    hpc = sub.add_parser(
        "hpc",
        help="Measure/estimate carbon footprint of an HPC batch job (sbatch etc.)",
    )
    hpc.add_argument(
        "action",
        choices=["report", "run", "detect"],
        help="report: footprint of the current/given job; "
        "run: wrap and measure a command; detect: show scheduler allocation",
    )
    hpc.add_argument("--job-id", default=None, help="Scheduler job id (SLURM sacct lookup)")
    hpc.add_argument("--zone", default=None, help="Electricity zone (e.g. PL, DE, FR)")
    hpc.add_argument("--api-key", default="", help="Electricity Maps API key")
    hpc.add_argument(
        "--elapsed", type=float, default=None,
        help="Wall-clock seconds (when not measured / no sacct)",
    )
    hpc.add_argument("--pue", type=float, default=None, help="Datacentre PUE (default 1.5)")
    hpc.add_argument(
        "--cpu-util", type=float, default=None,
        help="Assumed CPU utilisation 0..1 (default 1.0)",
    )
    hpc.add_argument(
        "--gpu-util", type=float, default=None,
        help="Assumed GPU utilisation 0..1 (default 1.0)",
    )
    hpc.add_argument(
        "--cpus", type=int, default=None,
        help="Override total CPU cores (when not inside a job)",
    )
    hpc.add_argument("--gpus", type=int, default=None, help="Override GPU count")
    hpc.add_argument("--nodes", type=int, default=None, help="Override node count")
    hpc.add_argument("--mem-gb", type=float, default=None, help="Override memory in GB")
    hpc.add_argument(
        "--no-sacct", action="store_true", help="Do not query SLURM sacct accounting"
    )
    hpc.add_argument(
        "--output", default=None, help="Write the JSON report to this file"
    )

    # Split off a wrapped command for `hpc run`: everything after the first
    # standalone "--" is the command, not flags for carbon-tracker itself.
    argv = sys.argv[1:]
    hpc_command: list = []
    if "--" in argv:
        idx = argv.index("--")
        hpc_command = argv[idx + 1:]
        argv = argv[:idx]

    args = parser.parse_args(argv)
    args.hpc_command = hpc_command

    if args.command == "monitor":
        _cmd_monitor(args)
    elif args.command == "project":
        _cmd_project(args)
    elif args.command == "detect":
        _cmd_detect()
    elif args.command == "hpc":
        _cmd_hpc(args)
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

    warned = False
    try:
        while True:
            time.sleep(5)
            snap = tracker.get_snapshot()

            if not warned and snap["total_seconds"] >= 5:
                warning = tracker.power_warning()
                if warning:
                    print(f"\n[!] {warning}\n")
                else:
                    print(
                        f"\n[OK] Measured real power draw from "
                        f"{snap['power_source']}.\n"
                    )
                warned = True

            elapsed = snap["total_seconds"]
            h, m, s = (
                int(elapsed) // 3600,
                (int(elapsed) % 3600) // 60,
                int(elapsed) % 60,
            )
            pwr = "battery" if not snap["power_estimated"] else "est"
            print(
                f"\r  {h}h{m:02d}m{s:02d}s | "
                f"CO2: {snap['total_carbon_grams']:.3f}g | "
                f"Energy: {snap['total_energy_kwh'] * 1000:.4f}Wh | "
                f"Grid: {snap['intensity']:.0f} gCO2/kWh"
                f"{'*' if snap['intensity_real'] else ''} | "
                f"Pwr: {pwr}    ",
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
        method = result.get("method", "average")
        print(f"Forecast for {result['projected_hours']:.1f} hours [{method}]:")
        print(f"  Projected CO2:    {result['projected_carbon_grams']:.2f} g")
        if method == "gaussian_mixture":
            print(
                f"    95% range:      "
                f"{result.get('carbon_low_grams', 0):.2f} - "
                f"{result.get('carbon_high_grams', 0):.2f} g"
            )
        print(f"  Projected Energy: {result['projected_energy_kwh'] * 1000:.2f} Wh")
        print(f"  Rate:             {result['rate_grams_per_hour']:.2f} gCO2/hour")
        comps = result.get("carbon_components", [])
        if len(comps) > 1:
            modes = ", ".join(
                f"{c['rate']:.1f} g/h ({c['weight'] * 100:.0f}%)" for c in comps
            )
            print(f"  Usage modes:      {modes}")
        print(
            f"  Based on:         {result['based_on_sessions']} sessions "
            f"({result['based_on_hours']:.1f}h)"
        )

        per_app = result.get("per_app", {})
        if per_app:
            print("  Per-app forecast (top 5 by CO2):")
            top = sorted(
                per_app.items(),
                key=lambda x: -x[1]["projected_carbon_grams"],
            )[:5]
            for name, app in top:
                print(
                    f"    {name:25s} "
                    f"CO2={app['projected_carbon_grams']:.2f}g  "
                    f"(±{(app['rate_std_grams_per_hour'] * result['projected_hours']):.2f}g)  "
                    f"Energy={app['projected_energy_kwh'] * 1000:.2f}Wh"
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


def _hpc_apply_overrides(job, args):
    """Apply CLI resource overrides onto a detected/blank HPCJobInfo."""
    if args.cpus is not None:
        job.num_cpus = args.cpus
    if args.gpus is not None:
        job.num_gpus = args.gpus
    if args.nodes is not None:
        job.num_nodes = args.nodes
    if args.mem_gb is not None:
        job.mem_mb = int(args.mem_gb * 1024)
    return job


def _cmd_hpc(args):
    from carbon_tracker.hpc import (
        HPCJobInfo,
        detect_hpc_job,
        build_hpc_report,
        run_and_measure,
    )

    from carbon_tracker.globals import (
        HPC_DEFAULT_PUE,
        HPC_DEFAULT_CPU_UTILIZATION,
        HPC_DEFAULT_GPU_UTILIZATION,
    )

    pue = args.pue if args.pue is not None else HPC_DEFAULT_PUE
    cpu_util = args.cpu_util if args.cpu_util is not None else HPC_DEFAULT_CPU_UTILIZATION
    gpu_util = args.gpu_util if args.gpu_util is not None else HPC_DEFAULT_GPU_UTILIZATION

    if args.action == "detect":
        job = detect_hpc_job()
        if not job:
            print("Not running inside a recognised HPC batch job "
                  "(SLURM/PBS/LSF/SGE).")
            print("Set --cpus/--gpus/--nodes manually with 'hpc report' to "
                  "estimate anyway.")
            return
        print("<== HPC Job Detection ==>")
        for k, v in job.to_dict().items():
            print(f"  {k:18s}: {v}")
        return

    # Resolve the job (detected or a blank one for manual overrides).
    job = detect_hpc_job() or HPCJobInfo()
    job = _hpc_apply_overrides(job, args)
    if args.job_id:
        job.job_id = args.job_id
        if not job.scheduler:
            job.scheduler = "slurm"

    measured_energy = None
    measured_source = ""
    elapsed = args.elapsed

    if args.action == "run":
        command = list(args.hpc_command or [])
        if not command:
            print("No command given. Usage: carbon-tracker hpc run [options] -- <command> [args]")
            return
        print(f"[carbon] Measuring: {' '.join(command)}\n")
        exit_code, elapsed, measured_energy, measured_source = run_and_measure(command)
        print(f"\n[carbon] Command exited with code {exit_code} after "
              f"{elapsed:.1f}s.\n")

    report = build_hpc_report(
        job=job,
        elapsed_seconds=elapsed,
        zone=args.zone,
        api_key=args.api_key,
        pue=pue,
        cpu_utilization=cpu_util,
        gpu_utilization=gpu_util,
        measured_energy_kwh=measured_energy,
        measured_source=measured_source,
        use_sacct=not args.no_sacct,
    )

    print(report.summary())
    print()
    print(report.manual_computation_report())

    if args.output:
        report.save(args.output)
        print(f"\nReport written to {args.output}")

    if args.action == "run":
        # Propagate the wrapped command's exit status to the scheduler.
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
