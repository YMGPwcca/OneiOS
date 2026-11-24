#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Paired, local-only OFF/ON benchmark of the freestanding ARM64 test kernel.

This does not boot an Apple image, use ADB or measure a physical phone.
Report medians of per-run statistics and paired ON/OFF mean-latency changes;
a median of per-run percentiles is not a pooled event percentile.
"""
import argparse
import hashlib
import json
import pathlib
import platform
import re
import shlex
import statistics
import subprocess
import tempfile
import time

# Match the current testkernel.c bench() labels, ignoring indentation.
METRICS = {
    "null syscall, round trip (kernel to kernel)": "syscall_round",
    "svc -> the kernel has the trap": "syscall_up",
    "the kernel releases -> user code runs": "syscall_down",
    "page fault filled by task_map, as user code sees it": "fault_resolve",
    "task_map (host call)": "task_map",
    "task_unmap (host call; queued while the thread is stopped)": "task_unmap",
    "timer interrupt of a running thread: deadline -> the kernel has the trap": "timer_kick",
    "ram_discard of one 16 KiB page (host call)": "discard_one",
    "ram_discard of 64 consecutive pages, 1 MiB (host call)": "discard_64",
    "zero-fill of a resident 16 KiB page": "fill_resident",
    "zero-fill of a 16 KiB page given back (the host fills it again)": "fill_given",
}
ROW = re.compile(r"BENCH\s+(.+?): n (\d+) mean (\d+) ns, p50 (\d+) p90 (\d+) p99 (\d+) ns\s*$")

def parse_log(text, scale, enabled):
    if "TESTKERNEL: all passed" not in text or "BENCH done" not in text:
        raise ValueError("test kernel or benchmark did not complete")
    if re.search(r"BENCH\s+(?:skipped:|\((?:other traps|failed calls or other traps):\s*[1-9])", text):
        raise ValueError("benchmark skipped or reported failed calls/other traps")
    if ("perf-task-wait: scope=process_total" in text) != bool(enabled):
        raise ValueError("unexpected profiler state in benchmark log")
    rows = {}
    for line in text.splitlines():
        m = ROW.search(line)
        if not m:
            continue
        label = m[1].strip()
        if label not in METRICS:
            continue
        key = METRICS[label]
        if key in rows:
            raise ValueError("duplicate benchmark row: " + key)
        rows[key] = dict(zip(("n", "mean_ns", "p50_ns", "p90_ns", "p99_ns"),
                             map(int, m.groups()[1:])))
    if set(rows) != set(METRICS.values()):
        raise ValueError("missing benchmark rows: " + str(set(METRICS.values()) - set(rows)))
    # Primary workloads must have exactly the intended number of samples.
    exact = {
        "syscall_round": 20000 * scale - 1,
        "fault_resolve": 5000 * scale,
        "task_map": 5000 * scale,
        "task_unmap": 5000 * scale,
        "discard_one": 3200 * scale,
        "discard_64": 50 * scale,
        "fill_resident": 3200 * scale,
        "fill_given": 3200 * scale,
    }
    for key, expected in exact.items():
        if rows[key]["n"] != expected:
            raise ValueError(f"{key}: expected {expected} samples, got {rows[key]['n']}")
    # The test kernel omits handoff and kick samples outside its clock checks.
    # Do not mistake those for zero latency or accept tiny sample sets.
    for key, expected in (("syscall_up", 20000 * scale - 1),
                          ("syscall_down", 20000 * scale - 1),
                          ("timer_kick", 2000 * scale)):
        n = rows[key]["n"]
        if not (expected * 0.95 <= n <= expected):
            raise ValueError(f"{key}: incomplete clock-valid samples ({n}/{expected})")
    return rows

def summarize(pairs):
    result = {}
    for key in METRICS.values():
        off = [p[0]["metrics"][key] for p in pairs]
        on = [p[1]["metrics"][key] for p in pairs]
        result[key] = {
            "off": {f: statistics.median(r[f] for r in off) for f in ("mean_ns", "p50_ns", "p90_ns", "p99_ns")},
            "on": {f: statistics.median(r[f] for r in on) for f in ("mean_ns", "p50_ns", "p90_ns", "p99_ns")},
            "off_n_range": [min(r["n"] for r in off), max(r["n"] for r in off)],
            "on_n_range": [min(r["n"] for r in on), max(r["n"] for r in on)],
            "paired_mean_change_pct": statistics.median(
                (b["mean_ns"] - a["mean_ns"]) * 100 / a["mean_ns"]
                for a, b in zip(off, on)) if all(a["mean_ns"] for a in off) else None,
        }
    return result

def benchmark_mode(machine, system, runner, allow_emulated):
    if system == "Linux" and machine in ("aarch64", "arm64") and not runner:
        return "native_arm64"
    if runner and allow_emulated:
        return "emulated_diagnostic_only"
    raise ValueError("performance benchmark requires native ARM64 Linux; QEMU is diagnostic only (explicit --allow-emulated)")

def self_test():
    assert benchmark_mode("aarch64", "Linux", "", False) == "native_arm64"
    assert benchmark_mode("x86_64", "Linux", "qemu-aarch64", True) == "emulated_diagnostic_only"
    for machine, system, runner, allow in (("x86_64", "Linux", "qemu-aarch64", False), ("x86_64", "Linux", "", True), ("arm64", "Darwin", "", False)):
        try:
            benchmark_mode(machine, system, runner, allow)
        except ValueError:
            continue
        raise AssertionError("non-native timing accepted as native")
    counts = [19999, 19999, 19999, 5000, 5000, 5000, 2000, 3200, 50, 3200, 3200]
    text = "TESTKERNEL: all passed\nBENCH done\n" + "\n".join(
        f"guest BENCH {name}: n {count} mean 100 ns, p50 80 p90 120 p99 200 ns"
        for name, count in zip(METRICS, counts))
    a = parse_log(text, 1, 0)
    b = parse_log(text.replace("mean 100", "mean 110") +
                  "\nperf-task-wait: scope=process_total", 1, 1)
    assert summarize([{0: {"metrics": a}, 1: {"metrics": b}}])["task_map"]["paired_mean_change_pct"] == 10
    bad = (text.replace("BENCH done", ""), text.replace("n 5000 ", "n 1 ", 1),
           text + "\nBENCH   (other traps: 1)", text + "\nperf-task-wait: scope=process_total",
           text.replace("BENCH done", "BENCH skipped: no task layer"))
    for log in bad:
        try:
            parse_log(log, 1, 0)
        except ValueError:
            continue
        raise AssertionError("invalid receipt accepted")
    print("profiler benchmark parser: PASS")

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def run(args):
    binary = pathlib.Path(args.binary).resolve(strict=True)
    image = pathlib.Path(args.image).resolve(strict=True)
    # An empty output directory is required; never overwrite previous evidence.
    root = pathlib.Path(args.output_dir).resolve() if args.output_dir else pathlib.Path(tempfile.mkdtemp(prefix="task-profiler-bench.", dir=binary.parent))
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("output directory is not empty: " + str(root))
    print("BENCH_DIR=" + str(root), flush=True)
    manifest = {
        "host": platform.platform(), "host_machine": platform.machine(),
        "runner": args.runner or "native ARM64", "timing_mode": args.timing_mode,
        "binary_sha256": sha256(binary), "kernel_sha256": sha256(image / "kernel.kc"),
        "pairs": args.pairs, "scale": args.scale, "timeout_s": args.timeout,
        "warmup_pairs": 1, "runs": [],
        "scope": "synthetic test kernel, not iOS or S26 Ultra",
    }
    def save_manifest():
        (root / "runs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    save_manifest()
    measured = []
    for i in range(args.pairs + 1):
        pair = {}
        # Warm both configurations once. Alternate AB/BA to reduce drift.
        order = (0, 1) if i % 2 == 0 else (1, 0)
        for enabled in order:
            tag = f"{'warmup' if i == 0 else f'pair-{i:02d}'}-{'on' if enabled else 'off'}"
            log = root / (tag + ".log")
            with tempfile.TemporaryDirectory(prefix="data.", dir=root) as data:
                cmd = shlex.split(args.runner) + [
                    str(binary), "--mode", "bench", "--image", str(image),
                    "--data", data, "--cpus", "3", "--ram", "256M",
                    "--set", "ram-giveback=1", "--set", f"perf-task={enabled}",
                    "--set", "perf-log=0", "--display", "none", "--no-input",
                    "--width", "64", "--height", "64", "--boot-args", f"testkernel-bench={args.scale}",
                ]
                began = time.monotonic()
                with log.open("wb") as f:
                    try:
                        subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=args.timeout)
                    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
                        raise RuntimeError(f"{tag} failed: {e}; log={log}") from e
                elapsed = time.monotonic() - began
            try:
                rows = parse_log(log.read_text(errors="replace"), args.scale, enabled)
            except ValueError as e:
                raise RuntimeError(f"{tag} rejected: {e}; log={log}") from e
            record = {"tag": tag, "profiler": enabled, "pair": i, "elapsed_s": elapsed,
                      "log": log.name, "command": cmd, "metrics": rows}
            pair[enabled] = record
            manifest["runs"].append(record)
            save_manifest()
            print(f"{tag}: PASS ({elapsed:.3f}s, including setup and teardown)", flush=True)
        if i:
            measured.append(pair)
    summary = summarize(measured)
    out = {"timing_mode": args.timing_mode, "host_machine": platform.machine(), "metrics": summary,
           "whole_process_elapsed_median_s": {
               str(enabled): statistics.median(p[enabled]["elapsed_s"] for p in measured)
               for enabled in (0, 1)},
           "notes": "Paired changes use per-run means; per-run percentiles may saturate at the test kernel's approximately 170 us histogram ceiling. This is not physical GPU/display FPS."}
    (root / "summary.json").write_text(json.dumps(out, indent=2) + "\n")
    print("\nmetric                OFF mean us  ON mean us  paired change %  OFF p99 us  ON p99 us")
    for key, r in summary.items():
        change = r["paired_mean_change_pct"]
        delta = "n/a" if change is None else f"{change:+.2f}"
        print(f"{key:21} {r['off']['mean_ns']/1000:11.3f} {r['on']['mean_ns']/1000:11.3f} {delta:>16} "
              f"{r['off']['p99_ns']/1000:11.3f} {r['on']['p99_ns']/1000:10.3f}")
    print("SUMMARY_JSON=" + str(root / "summary.json"))
    print("BENCHMARK_COMPLETE=PASS")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--runner", default="")
    parser.add_argument("--allow-emulated", action="store_true", help="diagnostic QEMU timings only; never hardware acceptance")
    parser.add_argument("--binary")
    parser.add_argument("--image")
    parser.add_argument("--output-dir")
    parser.add_argument("--pairs", type=int, default=6)
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.binary or not args.image or not 1 <= args.pairs <= 50 or not 1 <= args.scale <= 9 or args.timeout < 1:
        parser.error("require binary/image, pairs 1..50, scale 1..9 and positive timeout")
    try:
        args.timing_mode = benchmark_mode(platform.machine(), platform.system(), args.runner, args.allow_emulated)
    except ValueError as e:
        parser.error(str(e))
    print("TIMING_MODE=" + args.timing_mode, flush=True)
    run(args)

if __name__ == "__main__":
    main()
