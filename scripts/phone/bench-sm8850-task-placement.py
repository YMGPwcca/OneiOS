#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded native SM8850 placement A/B using the already validated P0 artifacts.

Normal Android, shell UID, synthetic guest only. Both variants inherit CPUs 0-2;
the candidate additionally requests the existing per-vCPU pairing (cpu-pin=2).
No root, takeover, global CPU policy change, or rebuild. No performance claim
about actual iOS frames or 4/6/8-vCPU production scheduling.
With --baseline-binary, use the archived P0 binary and current CI-built binary,
both with the current synthetic kernel, in a matched 2x2 mask/code experiment.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime/xnuhost/tests"))
from bench_task_profiler import parse_log, summarize, self_test as parser_self_test

SOURCE = "08a5b8576e8da8c10c3a2ac3d989bf75240cba3f"
ONEOS = "f5c1b4a44fc45d78987694a230f7ffabb213e99c"
BUILD = ROOT / "runtime/xnuhost/build/android"
FILES = {
    "xnuhost": "16587e4c88e4ab5d0bc23b80e00fc711ebb13c5265ebff79264f8b742f2c8a10",
    "testimage/kernel.kc": "c42b4df38ab1f0ee2a7e737a048b76683c1b79e4a802ce5eb72d30689c51e9d0",
    "testimage/os.img": "90cefe7883d605d209801b83af9561e0ce16a577f5f96dc3dbce90d39537d1f7",
}
AFFINITY = re.compile(r"perf-affinity: vcpu=(\d+) tid=(\d+) allowed=([0-9,-]+|unknown) migrations=(\d+|unknown) last_cpu=(-?\d+)")
BATTERY = re.compile(r"^\s*temperature:\s*(-?\d+)\s*$", re.M)
REMOTE_PATH = re.compile(r"/data/local/tmp/oneios-p0-placement\.[A-Za-z0-9]+")


def call(argv, limit=45, check=True):
    p = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, errors="replace", timeout=limit)
    if check and p.returncode != 0:
        raise RuntimeError(f"exit {p.returncode}: {shlex.join(argv)}\n{p.stdout[-6000:]}")
    return p


def git(*args):
    return call(["git", "-C", str(ROOT), *args]).stdout.strip()


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def placement(log, paired, allowed="0-2"):
    """Check final observed vCPU masks. Does not prove task twin affinity."""
    rows = {}
    for m in AFFINITY.finditer(log):
        vcpu, tid, mask, migrations, last = m.groups()
        i = int(vcpu)
        require(i not in rows, f"duplicate affinity row for vCPU {i}")
        rows[i] = dict(tid=int(tid), allowed=mask,
                       migrations=None if migrations == "unknown" else int(migrations),
                       last_cpu=int(last))
    require(set(rows) == {0, 1, 2}, "missing/unexpected vCPU affinity records")
    for i, row in rows.items():
        want = str(i) if paired else allowed
        require(row["allowed"] == want,
                f"vCPU {i}: requested {'paired' if paired else 'unpaired'}: expected {want}, observed {row['allowed']}")
    return rows


def battery_temp(text):
    m = BATTERY.search(text)
    require(m is not None, "battery temperature unavailable")
    n = int(m[1])
    require(0 <= n <= 800, "invalid battery temperature")
    return n / 10


def self_test():
    parser_self_test()
    def fixture(paired):
        return "\n".join(f"perf-affinity: vcpu={i} tid={100+i} allowed={i if paired else '0-2'} migrations=10 last_cpu={i}" for i in range(3))
    assert placement(fixture(False), False)[2]["allowed"] == "0-2"
    assert placement(fixture(True), True)[2]["allowed"] == "2"
    assert placement(fixture(False).replace("allowed=0-2", "allowed=0-7"), False, "0-7")[0]["allowed"] == "0-7"
    for bad, paired in [(fixture(False), True), (fixture(True), False),
                        (fixture(True).splitlines()[0], True),
                        (fixture(True) + "\n" + fixture(True), True),
                        (fixture(True).replace("allowed=1", "allowed=unknown"), True)]:
        try:
            placement(bad, paired)
        except RuntimeError:
            continue
        raise AssertionError("invalid placement receipt accepted")
    assert battery_temp("Current Battery Service state:\n  temperature: 360\n") == 36.0
    for bad in ("", "temperature: -1", "temperature: 900"):
        try:
            battery_temp(bad)
        except RuntimeError:
            continue
        raise AssertionError("invalid battery reading accepted")
    print("placement receipt parser: PASS")


def run(adb, baseline_binary=None):
    head = git("rev-parse", "HEAD")
    require(git("status", "--porcelain") == "", "dirty repository")
    require(git("-C", str(ROOT / "app"), "rev-parse", "HEAD") == ONEOS, "OneOS revision differs")
    call(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", SOURCE, head])
    if baseline_binary is None:
        call(["git", "-C", str(ROOT), "diff", "--quiet", SOURCE, head, "--", "runtime/xnuhost"])
        for name, digest in FILES.items():
            require(sha(BUILD / name) == digest, f"not the previously verified artifact: {name}")
        artifacts = [(BUILD / "xnuhost", "xnuhost", FILES["xnuhost"])]
        hashes = dict(FILES)
        configs = [("unpaired", "xnuhost", "7", "0-2", 0),
                   ("paired", "xnuhost", "7", "0-2", 2)]
        comparisons = [("pairing", "unpaired", "paired")]
    else:
        baseline_binary = Path(baseline_binary).resolve()
        require(sha(baseline_binary) == FILES["xnuhost"], "baseline binary is not the verified P0 artifact")
        candidate = BUILD / "xnuhost"
        candidate_sha = sha(candidate)
        require(candidate_sha != FILES["xnuhost"], "candidate binary not rebuilt")
        hashes = {"baseline/xnuhost": FILES["xnuhost"], "candidate/xnuhost": candidate_sha,
                  **{k: sha(BUILD / k) for k in FILES if k != "xnuhost"}}
        artifacts = [(baseline_binary, "baseline/xnuhost", FILES["xnuhost"]),
                     (candidate, "candidate/xnuhost", candidate_sha)]
        configs = [("base-narrow", "baseline/xnuhost", "7", "0-2", 0),
                   ("new-narrow", "candidate/xnuhost", "7", "0-2", 0),
                   ("new-wide", "candidate/xnuhost", "ff", "0-7", 0),
                   ("base-wide", "baseline/xnuhost", "ff", "0-7", 0)]
        comparisons = [("code_on_0-2", "base-narrow", "new-narrow"),
                       ("code_on_0-7", "base-wide", "new-wide"),
                       ("mask_baseline", "base-narrow", "base-wide"),
                       ("mask_candidate", "new-narrow", "new-wide")]
    for name in ("testimage/kernel.kc", "testimage/os.img"):
        artifacts.append((BUILD / name, "image/" + Path(name).name, hashes[name]))

    def adb_call(*args, check=True, limit=45):
        return call([adb, *args], check=check, limit=limit)
    def shell(cmd, check=True, limit=45):
        return adb_call("shell", "-n", "-T", cmd, check=check, limit=limit)
    def value(cmd):
        return shell(cmd).stdout.strip()
    def no_guest():
        p = shell("pidof xnuhost", check=False)
        require(p.returncode == 1 and not p.stdout.strip(), "existing xnuhost or failed process check")
    def safe_state():
        require(value("getprop sys.boot_completed") == "1", "Android is not booted")
        require(re.fullmatch(r"\d+(?:\s+\d+)*", value("pidof system_server")), "Android framework not running")
        no_guest()
        t = battery_temp(value("dumpsys battery"))
        # Conservative experiment admission only, not an override of firmware.
        require(t < 42.0, f"battery temperature {t:.1f} C: stop experiment and allow cooling")
        return t

    require(adb_call("get-state").stdout.strip() == "device", "ADB not ready")
    for cmd, expected in [("getprop ro.product.model", "SM-S948B"), ("getprop ro.soc.model", "SM8850"),
                          ("uname -m", "aarch64"), ("id -u", "2000")]:
        require(value(cmd) == expected, f"device identity or shell context mismatch: {cmd}")
    require(value("getprop ro.build.display.id").endswith("S948BXXS4BZIG"), "firmware changed; establish new baseline")
    shell("timeout -k 2 5 true")
    # Confirm that the normal shell may use precisely the common comparison
    # set. No root, system cpuset writes or attempts to enlarge allowed masks.
    require(value("taskset 7 sh -c 'grep ^Cpus_allowed_list: /proc/self/status'").split()[-1] == "0-2",
            "CPUs 0-2 are not all allowed; do not run placement comparison")
    if baseline_binary is not None:
        require(value("grep ^Cpus_allowed_list: /proc/self/status").split()[-1] == "0-7",
                "full 0-7 mask is not inherited; do not expand permissions")
        require(value("taskset ff sh -c 'grep ^Cpus_allowed_list: /proc/self/status'").split()[-1] == "0-7",
                "CPUs 0-7 unavailable")
    initial_temp = safe_state()
    out = Path(tempfile.mkdtemp(prefix="oneios-native-placement."))
    print(f"BENCH_DIR={out}", flush=True)
    remote = value("mktemp -d /data/local/tmp/oneios-p0-placement.XXXXXX")
    require(REMOTE_PATH.fullmatch(remote), "unexpected remote directory")
    manifest = {
        "source": SOURCE, "checkout": head, "oneos": ONEOS,
        "sha256": hashes, "timing_mode": "native_android_arm64",
        "scope": ("3-vCPU synthetic, matched binary/mask experiment with shared test kernel, not production iOS"
                  if baseline_binary is not None else
                  "3-vCPU synthetic, common inherited CPUs 0-2, not production iOS"),
        "warmup_pairs": 1, "measured_pairs": 3, "runs": [],
        "firmware": value("getprop ro.build.display.id"), "initial_battery_c": initial_temp,
    }

    def save():
        (out / "runs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    save()
    try:
        shell(f"mkdir {remote}/image")
        if baseline_binary is not None:
            shell(f"mkdir {remote}/baseline {remote}/candidate")
        for source_file, relative, digest in artifacts:
            dest = f"{remote}/{relative}"
            adb_call("push", str(source_file), dest)
            require(value(f"sha256sum {dest}").split()[0] == digest, f"remote hash mismatch: {relative}")
            if relative.endswith("xnuhost"):
                shell(f"chmod 700 {dest}")
                safe_state()
                p = shell(f"timeout -k 2 15 {dest} --selftest", check=False)
                (out / ("selftest-" + relative.replace("/", "-") + ".log")).write_text(p.stdout)
                require(p.returncode == 0 and "selftest: this host can run xnuhost" in p.stdout,
                        f"native selftest failed: {relative}")
        measured = []
        for i in range(4):
            pair = {}
            # Rotate condition order. One complete warmup block, three measured.
            ordered = configs[i % len(configs):] + configs[:i % len(configs)]
            for name, binary, mask, expected_mask, pin in ordered:
                before = safe_state()
                tag = f"pair-{i}-{name}"
                run_dir = f"{remote}/{tag}"
                shell(f"mkdir {run_dir}")
                argv = ["timeout", "-k", "2", "20", "taskset", mask, remote + "/" + binary,
                        "--mode", "bench", "--image", remote + "/image", "--data", run_dir,
                        "--cpus", "3", "--ram", "256M", "--gpu", "2d", "--display", "none",
                        "--no-input", "--width", "64", "--height", "64",
                        "--set", "bridges=0", "--set", f"cpu-pin={pin}",
                        "--set", "spin-host=0", "--set", "spin-task=0", "--set", "map-defer=1",
                        "--set", "ram-giveback=1", "--set", "perf-log=0", "--set", "perf-task=1",
                        "--boot-args", "testkernel-bench=1"]
                print(f"{tag}: start (battery {before:.1f} C)", flush=True)
                started = time.monotonic()
                p = shell(shlex.join(argv), check=False, limit=35)
                elapsed = time.monotonic() - started
                (out / (tag + ".log")).write_text(p.stdout)
                require(p.returncode == 0, f"{tag}: failed with code {p.returncode}; see {out}/{tag}.log")
                rows = parse_log(p.stdout, 1, 1)
                masks = placement(p.stdout, pin == 2, expected_mask)
                after = safe_state()
                record = {"tag": tag, "pair": i, "condition": name, "cpu_pin": pin,
                          "expected_mask": expected_mask, "binary": binary, "metrics": rows,
                          "vcpu_affinity": masks, "battery_before_c": before, "battery_after_c": after,
                          "adb_elapsed_s": elapsed, "command": argv, "log": tag + ".log"}
                manifest["runs"].append(record)
                save()
                pair[name] = record
                shell(f"rm -rf {run_dir}")
                print(f"{tag}: PASS; vCPU masks={[r['allowed'] for r in masks.values()]}; battery {after:.1f} C", flush=True)
                time.sleep(5)
            if i:
                measured.append(pair)
        summaries = {}
        for label, baseline, candidate in comparisons:
            summary = summarize([{0: block[baseline], 1: block[candidate]} for block in measured])
            summaries[label] = {"baseline": baseline, "candidate": candidate, "metrics": summary}
            print(f"===== {label}: {baseline} -> {candidate} =====")
            print(f"{'Metric':24} {'Baseline us':>13} {'Candidate us':>13} {'Delta %':>12}")
            for name, row in summary.items():
                delta = row["paired_mean_change_pct"]
                print(f"{name:24} {row['off']['mean_ns']/1000:13.3f} {row['on']['mean_ns']/1000:13.3f} "
                      + ("n/a" if delta is None else f"{delta:+12.2f}"))
        report = {"timing_mode": manifest["timing_mode"], "scope": manifest["scope"],
                  "comparisons": summaries}
        (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print("P1_MATRIX=PASS" if baseline_binary is not None else "PLACEMENT_BENCHMARK=PASS")
        print(f"BENCH_DIR={out}")
        print("Observed vCPU masks only; synthetic latency is not full iOS performance.")
    finally:
        try:
            no_guest()
            shell(f"rm -rf {remote}")
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            print(f"Cleanup not attempted/completed: {remote}: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--baseline-binary", type=Path,
                    help="archived verified P0 xnuhost; compare it with the CI-built current binary")
    ap.add_argument("--adb", default=os.environ.get("ADB", str(Path.home() / "Android/Sdk/platform-tools/adb")))
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    try:
        run(args.adb, args.baseline_binary)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as e:
        print("PLACEMENT_BENCHMARK=STOP: " + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
