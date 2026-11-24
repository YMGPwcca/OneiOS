#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Native CPU scaling and affinity study, only after the pinned local CI PASS.

No root, takeover, device bridges, clock/governor/thermal changes, or rebuild.
Group restriction applies to the whole synthetic runtime; it is not an
8-vCPU split assignment of six threads to cluster 0 and two to cluster 1.
"""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import statistics
import subprocess
import sys
import tempfile
import time

# Reuse the verified placement harness helpers and strict latency parser.
old = runpy.run_path(str(Path(__file__).with_name("bench-sm8850-task-placement.py")))
ROOT, BUILD, ONEOS = old["ROOT"], old["BUILD"], old["ONEOS"]
call, git, sha, require = (old[k] for k in ("call", "git", "sha", "require"))
parse_log, summarize, battery_temp = (old[k] for k in ("parse_log", "summarize", "battery_temp"))
AFFINITY = old["AFFINITY"]
CI_SOURCE = "72a54f6b13f725756500c23e0c4c370813647b31"
PAR_SCALE = 5
# (tag, vCPU count, inherited CPU mask, expected list, cpu-pin, workload)
CONFIGS = [
    ("latency-3-mask02", 3, "7", "0-2", 0, "latency"),
    ("latency-3-mask05", 3, "3f", "0-5", 0, "latency"),
    ("latency-3-mask07", 3, "ff", "0-7", 0, "latency"),
    ("parallel-2-regular", 2, "3", "0-1", 0, "parallel"),
    ("parallel-2-prime", 2, "c0", "6-7", 0, "parallel"),
    ("parallel-6-group", 6, "3f", "0-5", 0, "parallel"),
    ("parallel-6-pinned", 6, "3f", "0-5", 2, "parallel"),
    ("parallel-6-wide", 6, "ff", "0-7", 0, "parallel"),
    ("parallel-8-wide", 8, "ff", "0-7", 0, "parallel"),
    ("parallel-8-pinned", 8, "ff", "0-7", 2, "parallel"),
]
PAR_HEADER = re.compile(r"PARALLEL:\s*(\d+) vCPUs; each thread (\d+) rounds of (\d+) iterations and a system call")
PAR_ROW = re.compile(r"PARALLEL\s+(\d+) threads: (\d+) ms, speed-up (\d+\.\d+) \(ideal (\d+)\)")


def parse_parallel(log, ncpu, scale):
    header = PAR_HEADER.findall(log)
    require(header == [(str(ncpu), str(100 * scale), "100000")],
            "wrong/missing parallel workload header")
    require(log.count("PARALLEL done") == 1 and
            not re.search(r"PARALLEL\s+(?:skipped:|\(failed runs or other traps:)", log),
            "parallel workload failed or incomplete")
    expected = [n for n in (1, 2, 4, 8) if n <= ncpu]
    if expected[-1] != ncpu:
        expected.append(ncpu)
    rows = {}
    for n, ms, speedup, ideal in PAR_ROW.findall(log):
        n, ms = int(n), int(ms)
        require(n not in rows and int(ideal) == n and ms > 0,
                "duplicate or invalid parallel timing row")
        rows[n] = {"wall_ms": ms, "reported_speedup": float(speedup),
                   "rounds": n * 100 * scale}
    require(list(rows) == expected, f"parallel rows {list(rows)} != {expected}")
    return rows


def masks(log, ncpu, allowed, pin):
    rows = {}
    for v, tid, cpus, migrations, last in AFFINITY.findall(log):
        i = int(v)
        require(i not in rows, f"duplicate affinity row {i}")
        require(cpus == (str(i) if pin == 2 else allowed),
                f"vCPU {i}: unexpected actual allowed mask {cpus}")
        rows[i] = {"tid": int(tid), "allowed": cpus,
                   "migrations": None if migrations == "unknown" else int(migrations),
                   "last_cpu": int(last)}
    require(set(rows) == set(range(ncpu)), "missing/unexpected vCPU affinity rows")
    return rows


def self_test():
    old["self_test"]()
    for ncpu in (2, 6, 8):
        expected = [n for n in (1, 2, 4, 8) if n <= ncpu]
        if expected[-1] != ncpu:
            expected.append(ncpu)
        log = f"PARALLEL: {ncpu} vCPUs; each thread 500 rounds of 100000 iterations and a system call\n"
        log += "\n".join(f"PARALLEL {n} threads: 20 ms, speed-up {n}.00 (ideal {n})" for n in expected)
        log += "\nPARALLEL done\n"
        assert parse_parallel(log, ncpu, 5)[ncpu]["rounds"] == 500 * ncpu
        for bad in (log.replace("PARALLEL done", ""), log + "PARALLEL   (failed runs or other traps: 1)",
                    log.replace("20 ms", "0 ms"), log + f"PARALLEL {ncpu} threads: 20 ms, speed-up 1.00 (ideal {ncpu})"):
            try:
                parse_parallel(bad, ncpu, 5)
            except RuntimeError:
                continue
            raise AssertionError("invalid parallel log accepted")
        affinity = "\n".join(f"perf-affinity: vcpu={i} tid={100+i} allowed={i} migrations=0 last_cpu={i}" for i in range(ncpu))
        assert len(masks(affinity, ncpu, f"0-{ncpu-1}", 2)) == ncpu
        try:
            masks(affinity.replace("allowed=0 ", "allowed=0-7 "), ncpu, f"0-{ncpu-1}", 2)
        except RuntimeError:
            pass
        else:
            raise AssertionError("wrong pinned mask accepted")
    print("CPU scaling receipt parser: PASS")


def ci_receipt(path):
    candidates = [Path(path)] if path else sorted(
        Path("/tmp").glob("oneios-vm-display-ci.*.log"),
        key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates:
        text = p.read_text(errors="replace")
        if (re.search(r"^ci-local: checkout " + CI_SOURCE[:7] + r", mode=all,", text, re.M)
                and "ci-local: PASS - out/release/oneios-runtime-0.0.0-ci-arm64.tar.zst" in text):
            return p
    raise RuntimeError("no successful full local CI receipt for " + CI_SOURCE[:7])


def run(adb, ci_log):
    head = git("rev-parse", "HEAD")
    require(git("status", "--porcelain") == "", "dirty checkout")
    require(git("-C", str(ROOT / "app"), "rev-parse", "HEAD") == ONEOS, "OneOS mismatch")
    call(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", CI_SOURCE, head])
    call(["git", "-C", str(ROOT), "diff", "--quiet", CI_SOURCE, head, "--", "runtime", "app"])
    receipt = ci_receipt(ci_log)
    print("CI_RECEIPT=" + str(receipt), flush=True)
    hashes = {name: sha(BUILD / name) for name in ("xnuhost", "testimage/kernel.kc", "testimage/os.img")}

    def adb_call(*args, limit=45, check=True):
        return call([adb, *args], limit=limit, check=check)
    def shell(cmd, limit=45, check=True):
        return adb_call("shell", "-n", "-T", cmd, limit=limit, check=check)
    def value(cmd):
        return shell(cmd).stdout.strip()
    def no_guest():
        p = shell("pidof xnuhost", check=False)
        require(p.returncode == 1 and not p.stdout.strip(), "existing xnuhost or failed process check")
    def state(require_doze=True):
        require(value("getprop sys.boot_completed") == "1", "Android is not booted")
        require(re.fullmatch(r"\d+(?:\s+\d+)*", value("pidof system_server")), "Android framework not running")
        no_guest()
        if require_doze:
            require(value("dumpsys deviceidle get deep") == "IDLE" and
                    value("dumpsys deviceidle get screen") == "false", "Deep Doze/screen-off lost")
        t = battery_temp(value("dumpsys battery"))
        require(t < 42.0, f"battery {t:.1f} C: stop and allow cooling")
        return t

    require(adb_call("get-state").stdout.strip() == "device", "ADB not ready")
    for cmd, want in (("getprop ro.product.model", "SM-S948B"), ("getprop ro.soc.model", "SM8850"),
                      ("uname -m", "aarch64"), ("id -u", "2000")):
        require(value(cmd) == want, f"wrong device/UID: {cmd}")
    firmware = value("getprop ro.build.display.id")
    require(firmware.endswith("S948BXXS4BZIG"), "firmware changed")
    require(value("grep ^Cpus_allowed_list: /proc/self/status").split()[-1] == "0-7", "shell mask differs")
    for _, _, mask, allowed, _, _ in CONFIGS:
        require(value(f"taskset {mask} sh -c 'grep ^Cpus_allowed_list: /proc/self/status'").split()[-1] == allowed,
                f"mask {allowed} unavailable")
    for i in range(8):
        cap = value(f"cat /sys/devices/system/cpu/cpu{i}/cpu_capacity")
        cluster = value(f"cat /sys/devices/system/cpu/cpu{i}/cpufreq/related_cpus").split()
        require(cap == ("741" if i < 6 else "1024") and
                cluster == (list("012345") if i < 6 else ["6", "7"]), "topology changed")
    shell("timeout -k 2 5 true")
    state(False)
    forced = value("dumpsys deviceidle get force")
    require(forced in ("true", "false"), "unknown initial force-idle state")
    own_force = False
    remote = None
    out = Path(tempfile.mkdtemp(prefix="oneios-cpu-scaling."))
    print(f"BENCH_DIR={out}", flush=True)
    manifest = {"checkout": head, "runtime_source": CI_SOURCE, "oneos": ONEOS,
                "ci_log": str(receipt), "ci_log_sha256": sha(receipt),
                "sha256": hashes, "firmware": firmware, "timing_mode": "native_android_arm64",
                "warmup_blocks": 1, "measured_blocks": 3, "parallel_scale": PAR_SCALE, "runs": []}

    def save():
        (out / "runs.json").write_text(json.dumps(manifest, indent=2) + "\n")

    try:
        shell("input keyevent 223")
        time.sleep(3)
        if forced == "false":
            own_force = True
            print(value("dumpsys deviceidle force-idle deep"), flush=True)
        time.sleep(30)
        state()
        candidate = value("mktemp -d /data/local/tmp/oneios-cpu-scaling.XXXXXX")
        require(re.fullmatch(r"/data/local/tmp/oneios-cpu-scaling\.[A-Za-z0-9]+", candidate), "unexpected staging path")
        remote = candidate
        shell(f"mkdir {remote}/image")
        for name, digest in hashes.items():
            dest = f"{remote}/xnuhost" if name == "xnuhost" else f"{remote}/image/{Path(name).name}"
            adb_call("push", str(BUILD / name), dest)
            require(value(f"sha256sum {dest}").split()[0] == digest, f"remote hash differs: {name}")
        shell(f"chmod 700 {remote}/xnuhost")
        p = shell(f"timeout -k 2 15 {remote}/xnuhost --selftest", check=False)
        (out / "selftest.log").write_text(p.stdout)
        require(p.returncode == 0 and "selftest: this host can run xnuhost" in p.stdout, "native selftest failed")
        save()
        blocks = []
        for i in range(4):
            records = {}
            # Warm every condition once; measured blocks alternate forward/reverse
            # and rotate starts to reduce simple time/order effects.
            seq = CONFIGS[i:] + CONFIGS[:i]
            if i % 2:
                seq = list(reversed(seq))
            for name, ncpu, mask, allowed, pin, kind in seq:
                before = state()
                tag = f"block-{i}-{name}"
                data = f"{remote}/{tag}"
                shell(f"mkdir {data}")
                bootarg = "testkernel-bench=1" if kind == "latency" else f"testkernel-parallel={PAR_SCALE}"
                argv = ["timeout", "-k", "2", "20", "taskset", mask, remote + "/xnuhost",
                        "--mode", "bench", "--image", remote + "/image", "--data", data,
                        "--cpus", str(ncpu), "--ram", "256M", "--gpu", "2d", "--display", "none",
                        "--no-input", "--width", "64", "--height", "64", "--set", "bridges=0",
                        "--set", f"cpu-pin={pin}", "--set", "spin-host=0", "--set", "spin-task=0",
                        "--set", "map-defer=1", "--set", "ram-giveback=1", "--set", "perf-log=0",
                        "--set", "perf-task=1", "--boot-args", bootarg]
                print(f"{tag}: start (battery {before:.1f} C)", flush=True)
                started = time.monotonic()
                p = shell(shlex.join(argv), limit=35, check=False)
                elapsed = time.monotonic() - started
                (out / (tag + ".log")).write_text(p.stdout)
                require(p.returncode == 0, f"{tag}: exit {p.returncode}, see log")
                metrics = parse_log(p.stdout, 1, 1) if kind == "latency" else parse_parallel(p.stdout, ncpu, PAR_SCALE)
                actual = masks(p.stdout, ncpu, allowed, pin)
                after = state()
                record = {"tag": tag, "block": i, "condition": name, "ncpu": ncpu, "mask": allowed,
                          "cpu_pin": pin, "workload": kind, "command": argv,
                          "battery_before_c": before, "battery_after_c": after, "elapsed_s": elapsed,
                          "affinity": actual, "metrics": metrics, "log": tag + ".log"}
                manifest["runs"].append(record)
                records[name] = record
                save()
                print(f"{tag}: PASS masks={[r['allowed'] for r in actual.values()]} battery={after:.1f} C", flush=True)
                shell(f"rm -rf {data}")
                time.sleep(5)
            if i:
                blocks.append(records)

        results = {}
        print("===== 3-vCPU LATENCY: MEDIAN PER-RUN MEANS (us) =====")
        names = [c[0] for c in CONFIGS if c[-1] == "latency"]
        for name in names[1:]:
            result = summarize([{0: b[names[0]], 1: b[name]} for b in blocks])
            results[name] = result
            print(f"----- {names[0]} -> {name} -----")
            for k, v in result.items():
                d = v["paired_mean_change_pct"]
                print(f"{k:24} {v['off']['mean_ns']/1000:10.3f} -> {v['on']['mean_ns']/1000:10.3f} us; "
                      + ("n/a" if d is None else f"{d:+.2f}% paired"))
        print("===== PARALLEL: ALL CONFIGURED vCPUs ACTIVE =====")
        parallel = {}
        for name, ncpu, _, allowed, pin, kind in CONFIGS:
            if kind != "parallel":
                continue
            rows = [b[name]["metrics"][ncpu] for b in blocks]
            med_ms = statistics.median(r["wall_ms"] for r in rows)
            rate = statistics.median(1000 * r["rounds"] / r["wall_ms"] for r in rows)
            speed = statistics.median(r["reported_speedup"] for r in rows)
            parallel[name] = {"vcpus": ncpu, "mask": allowed, "pin": pin,
                              "median_wall_ms": med_ms, "median_rounds_per_s": rate,
                              "median_reported_speedup": speed}
            print(f"{name:24} {med_ms:7.1f} ms  {rate:10.0f} rounds/s  {speed:.2f}x")
        print("===== MATCHED PARALLEL WALL-TIME CHANGES =====")
        changes = {}
        for a, b in (("parallel-2-regular", "parallel-2-prime"),
                     ("parallel-6-group", "parallel-6-pinned"),
                     ("parallel-6-group", "parallel-6-wide"),
                     ("parallel-8-wide", "parallel-8-pinned")):
            n = parallel[a]["vcpus"]
            delta = statistics.median(
                100 * (r[b]["metrics"][n]["wall_ms"] - r[a]["metrics"][n]["wall_ms"]) /
                r[a]["metrics"][n]["wall_ms"] for r in blocks)
            changes[f"{a}->{b}"] = delta
            print(f"{a} -> {b}: {delta:+.2f}% paired (lower wall time is better)")
        (out / "summary.json").write_text(json.dumps(
            {"latency": results, "parallel": parallel, "parallel_paired_wall_change_pct": changes,
             "scope": "synthetic; observed vCPU masks only, not production iOS FPS or task thread residency"}, indent=2) + "\n")
        state()
        print("CPU_SCALING_BENCHMARK=PASS")
        print(f"BENCH_DIR={out}")
    finally:
        if remote is not None:
            try:
                no_guest()
                shell(f"rm -rf {remote}")
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                print(f"Cleanup not completed: {remote}: {e}", file=sys.stderr)
        if own_force:
            try:
                print("===== RESTORE NORMAL IDLE POLICY =====")
                print(value("dumpsys deviceidle unforce"))
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                print(f"Could not release forced Doze: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--ci-log", type=Path, help="successful local CI log; auto-discover matching /tmp log if omitted")
    parser.add_argument("--adb", default=os.environ.get("ADB", str(Path.home() / "Android/Sdk/platform-tools/adb")))
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    try:
        run(args.adb, args.ci_log)
    except (RuntimeError, ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as e:
        print(f"CPU_SCALING_BENCHMARK=STOP: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
