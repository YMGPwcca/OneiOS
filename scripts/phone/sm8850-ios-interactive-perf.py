#!/usr/bin/env python3
"""Read-only OneiOS iOS 27 GUI latency triage from existing host/display logs.

Never boots, remounts, touches an APFS image, changes a sysctl, or invokes ADB.
Display posting rate includes idle intervals; 'active cadence' is an estimate
from short gaps between *posted* buffers, not guaranteed actual iOS animation FPS.
"""

import argparse
import json
import re
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "out/sm8850/gpu-acceptance"
MAX_HOST = 64 << 20
MAX_DISPLAY = 8 << 20


def _numbers(line):
    return {key: value for key, value in re.findall(r"\b([a-z][a-z0-9_]*)=([0-9]+(?:\.[0-9]+)?)\b", line)}


def _values(text, pattern, cast=int):
    return [cast(m) for m in re.findall(pattern, text)]


def analyze_logs(host, display):
    """Return descriptive evidence only: no inferred root cause or fake FPS."""
    windows = []
    for line in display.splitlines():
        if "oneios-display: perf:" not in line:
            continue
        values = _numbers(line)
        required = {"mono_ms", "window_ms", "posts", "posted_rate", "active_cadence",
                    "active_gaps", "lock_p95_us", "copy_p95_us", "post_p95_us",
                    "gap_p95_us", "lock_max_us", "copy_max_us", "post_max_us"}
        if not required.issubset(values):
            continue
        windows.append({key: float(value) if "." in value else int(value)
                        for key, value in values.items()})
    active = [float(row["active_cadence"]) for row in windows
              if row["active_gaps"] >= 3 and float(row["active_cadence"]) > 0]
    lock_peak = max((row["lock_max_us"] for row in windows), default=0)
    copy_peak = max((row["copy_max_us"] for row in windows), default=0)
    post_peak = max((row["post_max_us"] for row in windows), default=0)
    host_gaps = _values(host, r"input: touch:[^\n]*?guest's next frame ([0-9]+\.[0-9]+) ms", float)
    cpu_traps = _values(host, r"xnuhost I perf: [0-9]+(?:\.[0-9]+)? s(?: since the start)?: [0-9]+ task traps \(([0-9]+(?:\.[0-9]+)?)/s\)", float)
    gpu_fences = _values(host, r"gpu: [0-9]+ s host: backboardd fences (\d+)")
    gpu_max = _values(host, r"gpu: [0-9]+ s host: backboardd fences \d+, submit->retired mean \d+ us max (\d+) us")
    memory = _values(host, r"memory: host MemAvailable (\d+) MiB")
    icons = _values(host, r"oneios-cpu: [^\n]*?iconservicesagent\[\d+\] (\d+)%")
    springboard = list(dict.fromkeys(_values(host, r"SpringBoard\[(\d+)\]")))
    backboardd = list(dict.fromkeys(_values(host, r"backboardd\[(\d+)\]")))
    warnings = host.count("host_statistics64() count is larger than expected")
    no_frame = len(re.findall(r"input: touch:[^\n]*no guest frame after the touch-down", host))
    return {
        "display": {
            "instrumentation_present": bool(windows), "windows": len(windows),
            "window_samples": windows,
            "posted_rate_max": max((float(row["posted_rate"]) for row in windows), default=None),
            "active_cadence_median": round(median(active), 2) if active else None,
            "active_cadence_windows": len(active),
            "lock_max_us": lock_peak if windows else None,
            "copy_max_us": copy_peak if windows else None,
            "post_max_us": post_peak if windows else None,
        },
        "touch": {"next_frame_latency_ms": host_gaps,
                  "max_next_frame_ms": max(host_gaps, default=None),
                  "no_subsequent_guest_frame": no_frame},
        "gpu": {"fence_intervals": len(gpu_fences),
                "fences_reported": sum(gpu_fences),
                "max_submit_to_retire_us": max(gpu_max, default=None)},
        "cpu": {"host_traps_per_second_max": max(cpu_traps, default=None),
                "iconservicesagent_percent_of_one_core_max": max(icons, default=None)},
        "processes": {"springboard_pids": springboard,
                      "backboardd_pids": backboardd,
                      "possible_ui_restart": len(springboard) > 1 or len(backboardd) > 1},
        "memory": {"android_memavailable_mib_min": min(memory, default=None),
                   "host_statistics64_abi_warning_lines": warnings},
        "settings_icons": {"first_vs_second_open_delay": "manual observation required"},
        "caveats": ["Window posting rate counts static/idle time; it is not iOS animation FPS.",
                    "Active cadence uses adjacent post gaps <=250 ms and excludes idle periods; it is an estimate, not measured guest refresh rate.",
                    "GPU fences, touch-to-frame latency, and display buffer timing measure different stages; correlation is not causation.",
                    "PID changes support a restart but cannot identify crash cause without death/CrashReporter evidence."]
    }


def _read(path, limit):
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f"log missing or larger than {limit} bytes: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def _latest_pair():
    candidates = sorted(LOG_DIR.glob("*-visual-xnuhost.log"), reverse=True)
    for host in candidates:
        display = Path(str(host).replace("-visual-xnuhost.log", "-visual-display.log"))
        if display.is_file():
            return host, display
    raise ValueError(f"no matching visual host/display log pair in {LOG_DIR}")


def _show(report):
    display = report["display"]
    print("DISPLAY_PERF_AVAILABLE=" + str(display["instrumentation_present"]))
    print("DISPLAY_5S_WINDOWS=" + str(display["windows"]))
    print("DISPLAY_POST_RATE_PEAK=" + str(display["posted_rate_max"]))
    print("DISPLAY_ACTIVE_CADENCE_MEDIAN_EST=" + str(display["active_cadence_median"]))
    print("DISPLAY_ANATIVEWINDOW_LOCK_MAX_MS=" + (str(round(display["lock_max_us"] / 1000, 2)) if display["lock_max_us"] is not None else "UNKNOWN"))
    print("DISPLAY_FRAME_COPY_MAX_MS=" + (str(round(display["copy_max_us"] / 1000, 2)) if display["copy_max_us"] is not None else "UNKNOWN"))
    print("DISPLAY_UNLOCK_POST_MAX_MS=" + (str(round(display["post_max_us"] / 1000, 2)) if display["post_max_us"] is not None else "UNKNOWN"))
    print("TOUCH_TO_FRAME_MAX_MS=" + str(report["touch"]["max_next_frame_ms"]))
    print("TOUCH_NO_GUEST_FRAME=" + str(report["touch"]["no_subsequent_guest_frame"]))
    print("GPU_FENCE_MAX_MS=" + (str(round(report["gpu"]["max_submit_to_retire_us"] / 1000, 2)) if report["gpu"]["max_submit_to_retire_us"] is not None else "UNKNOWN"))
    print("HOST_TRAPS_PER_SEC_MAX=" + str(report["cpu"]["host_traps_per_second_max"]))
    print("ICONSERVICE_CPU_PEAK_PERCENT=" + str(report["cpu"]["iconservicesagent_percent_of_one_core_max"]))
    print("SPRINGBOARD_PIDS=" + ",".join(map(str,report["processes"]["springboard_pids"])))
    print("BACKBOARDD_PIDS=" + ",".join(map(str,report["processes"]["backboardd_pids"])))
    print("ANDROID_MEMAVAILABLE_MIN_MIB=" + str(report["memory"]["android_memavailable_mib_min"]))
    print("ABI_WARNINGS=" + str(report["memory"]["host_statistics64_abi_warning_lines"]))
    print("SETTINGS_ICON_COLD_WARM_LATENCY=MANUAL_OBSERVATION_REQUIRED")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--xnuhost", type=Path, help="saved xnuhost log")
    p.add_argument("--display", type=Path, help="saved oneios-display log")
    p.add_argument("--json", type=Path, help="write read-only evidence report JSON")
    args = p.parse_args(argv)
    if bool(args.xnuhost) != bool(args.display):
        p.error("--xnuhost and --display must be supplied together")
    try:
        host_path, display_path = (args.xnuhost, args.display) if args.xnuhost else _latest_pair()
        report = analyze_logs(_read(host_path, MAX_HOST), _read(display_path, MAX_DISPLAY))
        report["sources"] = {"xnuhost": str(host_path), "display": str(display_path)}
        _show(report)
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
            print("PERF_REPORT=" + str(args.json))
    except (OSError, ValueError) as exc:
        p.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
