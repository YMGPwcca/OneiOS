#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Matched headless CPU study in the existing 20-second Framework-only smoke.

Prepare before stopping Framework, reuse exact CI artifacts, run as UID 2000.
Never extend the existing device deadline or change a thermal/CPU/return gate.
This is a one-block exploratory A/B; partial results are preserved.
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

HERE = Path(__file__).resolve().parent
cpu = runpy.run_path(str(HERE / "bench-sm8850-cpu-scaling.py"))
takeover = runpy.run_path(str(HERE / "sm8850-takeover.py"))
ROOT, BUILD, ONEOS, CI_SOURCE = (cpu[k] for k in ("ROOT", "BUILD", "ONEOS", "CI_SOURCE"))
call, git, sha, require = (cpu[k] for k in ("call", "git", "sha", "require"))
parse_log, parse_parallel, masks = (cpu[k] for k in ("parse_log", "parse_parallel", "masks"))
battery_temp = cpu["battery_temp"]
CASES = [c for c in cpu["CONFIGS"] if c[0] in (
    "latency-3-mask02", "latency-3-mask05", "parallel-6-pinned", "parallel-8-wide")]
LIMIT = 3
# The existing smoke is only 20 s after verified stop. Reserve several
# seconds for return. An incomplete case is not timing evidence.
RESERVE = 4
SCALE = cpu["PAR_SCALE"]


def remaining(deadline, uptime):
    require(re.fullmatch(r"\d+", str(deadline)), "invalid device deadline")
    require(re.fullmatch(r"\d+(?:\.\d+)?", str(uptime)), "invalid device uptime")
    return int(deadline) - float(uptime)


def argv_for(remote, name, ncpu, mask, pin, kind, arm):
    bootarg = "testkernel-bench=1" if kind == "latency" else f"testkernel-parallel={SCALE}"
    return ["timeout", "-k", "1", str(LIMIT), "taskset", mask, remote + "/xnuhost",
            "--mode", "bench", "--image", remote + "/image", "--data", f"{remote}/{arm}-{name}",
            "--cpus", str(ncpu), "--ram", "256M", "--gpu", "2d", "--display", "none",
            "--no-input", "--width", "64", "--height", "64", "--set", "bridges=0",
            "--set", f"cpu-pin={pin}", "--set", "spin-host=0", "--set", "spin-task=0",
            "--set", "map-defer=1", "--set", "ram-giveback=1", "--set", "perf-log=0",
            "--set", "perf-task=1", "--boot-args", bootarg]


def self_test():
    cpu["self_test"]()
    assert remaining("120", "101.5") == 18.5
    assert remaining("120", "116.1") < RESERVE
    for bad in ("", "-1", "120; reboot"):
        try:
            remaining(bad, "100")
        except RuntimeError:
            pass
        else:
            raise AssertionError("invalid deadline accepted")
    assert len(CASES) == 4
    for name, ncpu, mask, allowed, pin, kind in CASES:
        a = argv_for("/data/local/tmp/test", name, ncpu, mask, pin, kind, "on")
        b = argv_for("/data/local/tmp/test", name, ncpu, mask, pin, kind, "off")
        assert [x for x in a if "/on-" not in x] == [x for x in b if "/off-" not in x]
        assert "bridges=0" in a and "none" in a and "2d" in a
    print("Framework-state benchmark plan/parser: PASS (offline only)")


def run(args):
    require(git("status", "--porcelain") == "", "dirty checkout")
    require(git("-C", str(ROOT / "app"), "rev-parse", "HEAD") == ONEOS, "OneOS mismatch")
    head = git("rev-parse", "HEAD")
    call(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", CI_SOURCE, head])
    call(["git", "-C", str(ROOT), "diff", "--quiet", CI_SOURCE, head, "--", "runtime", "app"])
    ci_log = cpu["ci_receipt"](args.ci_log)
    artifacts = ("xnuhost", "testimage/kernel.kc", "testimage/os.img")
    hashes = {name: sha(BUILD / name) for name in artifacts}
    phone = takeover["Phone"](Path(args.adb), args.serial)
    out = Path(tempfile.mkdtemp(prefix="oneios-framework-cpu."))
    print(f"CI_RECEIPT={ci_log}\nBENCH_DIR={out}", flush=True)
    remote = None
    own_force = False
    results = {}
    manifest = {"checkout": head, "runtime_source": CI_SOURCE, "oneos": ONEOS,
                "ci_log": str(ci_log), "sha256": hashes, "runs": results,
                "scope": "one matched block; no physical FPS or recovery certification"}

    def save():
        (out / "runs.json").write_text(json.dumps(manifest, indent=2) + "\n")

    def sh(cmd, check=True, limit=10):
        return call(phone.command + ["shell", "-n", "-T", cmd], check=check, limit=limit)

    def value(cmd):
        return sh(cmd).stdout.strip()

    def no_guest():
        p = sh("pidof xnuhost", check=False)
        require(p.returncode == 1 and not p.stdout.strip(), "another guest or failed process check")

    def check_common():
        require(value("id -u") == "2000", "benchmark must run as normal Android shell")
        require(value("getenforce") == "Enforcing", "SELinux changed")
        require(value("getprop ro.build.display.id").endswith("S948BXXS4BZIG"), "firmware differs")
        require(value("grep ^Cpus_allowed_list: /proc/self/status").split()[-1] == "0-7",
                "inherited CPU mask differs")
        no_guest()

    def on_state():
        require(value("getprop sys.boot_completed") == "1" and
                re.fullmatch(r"\d+(?:\s+\d+)*", value("pidof system_server")),
                "Framework not healthy")
        require(value("dumpsys deviceidle get deep") == "IDLE" and
                value("dumpsys deviceidle get screen") == "false", "baseline not Deep Doze/screen off")
        t = battery_temp(value("dumpsys battery"))
        require(t < 35.0, f"battery {t:.1f} C; cool device before trial")
        return t

    def measure(case, arm, timeout):
        name, ncpu, mask, allowed, pin, kind = case
        argv = argv_for(remote, name, ncpu, mask, pin, kind, arm)
        tag = f"{arm}-{name}"
        # No root payload. During OFF, the caller has confirmed the existing
        # framework stop marker and the command also verifies no system_server.
        pre = ("test \"$(getprop init.svc.zygote)\" = stopped && "
               "! pidof system_server >/dev/null 2>&1 && " if arm == "off" else
               "pidof system_server >/dev/null 2>&1 && ")
        p = sh(pre + shlex.join(argv), check=False, limit=timeout)
        (out / (tag + ".log")).write_text(p.stdout)
        require(p.returncode == 0, f"{tag}: exit {p.returncode}; timing rejected")
        metrics = parse_log(p.stdout, 1, 1) if kind == "latency" else parse_parallel(p.stdout, ncpu, SCALE)
        observed = masks(p.stdout, ncpu, allowed, pin)
        record = {"condition": name, "arm": arm, "ncpu": ncpu, "mask": allowed,
                  "pin": pin, "metrics": metrics, "affinity": observed,
                  "command": argv, "log": tag + ".log"}
        results[tag] = record
        save()
        print(f"{tag}: PASS masks={[r['allowed'] for r in observed.values()]}", flush=True)

    try:
        check_common()
        require(value("getprop sys.boot_completed") == "1", "Android not booted")
        require(battery_temp(value("dumpsys battery")) < 35.0, "battery must be cool")
        boot = value("cat /proc/sys/kernel/random/boot_id")
        manifest["boot"] = boot
        candidate = value("mktemp -d /data/local/tmp/oneios-framework-cpu.XXXXXX")
        require(re.fullmatch(r"/data/local/tmp/oneios-framework-cpu\.[A-Za-z0-9]+", candidate),
                "unexpected remote path")
        remote = candidate
        sh(f"mkdir {remote}/image")
        for name, digest in hashes.items():
            dest = f"{remote}/xnuhost" if name == "xnuhost" else f"{remote}/image/{Path(name).name}"
            call(phone.command + ["push", str(BUILD / name), dest], limit=45)
            require(value(f"sha256sum {dest}").split()[0] == digest, "remote artifact hash mismatch")
        sh(f"chmod 700 {remote}/xnuhost")
        for case in CASES:
            for arm in ("on", "off"):
                sh(f"mkdir {remote}/{arm}-{case[0]}")
            require(value(f"taskset {case[2]} sh -c 'grep ^Cpus_allowed_list: /proc/self/status'").split()[-1] == case[3],
                    "requested mask unavailable")
        p = sh(f"timeout -k 2 15 {remote}/xnuhost --selftest", check=False, limit=20)
        (out / "selftest.log").write_text(p.stdout)
        require(p.returncode == 0 and "selftest: this host can run xnuhost" in p.stdout, "native selftest failed")
        forced = value("dumpsys deviceidle get force")
        require(forced == "false", "release any preexisting forced idle manually before trial")
        sh("input keyevent 223")
        time.sleep(3)
        own_force = True
        sh("dumpsys deviceidle force-idle deep")
        time.sleep(30)
        print("===== FRAMEWORK ON BASELINE =====", flush=True)
        for case in CASES:
            check_common()
            before = on_state()
            measure(case, "on", LIMIT + 4)
            after = on_state()
            results["on-" + case[0]].update(battery_before_c=before, battery_after_c=after)
            save()
        sh("dumpsys deviceidle unforce")
        own_force = False

        def ready(p, state, expected_boot, token):
            require(expected_boot == boot, "boot changed before OFF arm")
            require(takeover["reboot_smoke_ready"](state, boot, token), "invalid framework stop receipt")
            kv = dict(line.split("=", 1) for line in state.splitlines() if "=" in line)
            deadline = kv.get("control/framework.deadline", "")
            manifest["off_launch"] = token
            manifest["off_deadline"] = deadline
            save()
            print("===== FRAMEWORK OFF: EXISTING 20S WINDOW =====", flush=True)
            # All files, hashes, data directories and baseline measurements are
            # prepared before this point; no root checks or framework Binder
            # calls inside the workload. Do not extend the recovery deadline.
            # Use one short shell check and reject if there is insufficient time.
            common = value("echo $(id -u) $(getenforce) $(cat /proc/sys/kernel/random/boot_id); grep ^Cpus_allowed_list: /proc/self/status; head -c 100 /proc/uptime").split()
            require(common[:3] == ["2000", "Enforcing", boot] and len(common) >= 6 and common[4] == "0-7",
                    "OFF shell context differs")
            for case in CASES:
                uptime = value("cut -d' ' -f1 /proc/uptime")
                left = remaining(deadline, uptime)
                if left < LIMIT + 1 + RESERVE:
                    print(f"FRAMEWORK_OFF_BUDGET_EXHAUSTED remaining={left:.1f}s", flush=True)
                    break
                try:
                    measure(case, "off", min(LIMIT + 2, left - RESERVE))
                except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as e:
                    print(f"OFF case incomplete: {e}", flush=True)
                    break

        # No new stop commands, no profile token enabling thermal-off mode,
        # no recovery/thermal policy patch, no APFS data rearm/guest boot.
        # The existing launch function still owns all admissions and return.
        session = out / "existing-smoke"
        session.mkdir(mode=0o700)
        status = takeover["launch"](phone, "smoke", session, reboot_only=True,
                                    on_reboot_smoke_ready=ready)
        manifest["lifecycle_exit"] = status
        save()
        print("===== MATCHED FRAMEWORK STATE RESULTS =====")
        matched = 0
        for name, ncpu, _, _, _, kind in CASES:
            a, b = results.get("on-" + name), results.get("off-" + name)
            if not (a and b):
                print(f"{name}: INCOMPLETE")
                continue
            matched += 1
            if kind == "latency":
                for metric in ("syscall_round", "fault_resolve", "timer_kick"):
                    x, y = (r["metrics"][metric]["mean_ns"] / 1000 for r in (a,b))
                    print(f"{name} {metric}: {x:.3f} -> {y:.3f} us")
            else:
                x, y = (r["metrics"][ncpu]["wall_ms"] for r in (a,b))
                print(f"{name}: {x} -> {y} ms; {1000*ncpu*100*SCALE/x:.0f} -> {1000*ncpu*100*SCALE/y:.0f} rounds/s")
        print(f"FRAMEWORK_CPU_BENCHMARK_MATCHED={matched}/{len(CASES)}")
        print("One matched block only; different idle/clock/thermal conditions may confound results.")
        print(f"BENCH_DIR={out}")
        require(matched > 0, "no completed OFF workload")
    finally:
        if own_force:
            try:
                sh("dumpsys deviceidle unforce")
            except (RuntimeError, subprocess.SubprocessError) as e:
                print(f"Could not restore forced idle: {e}", file=sys.stderr)
        if remote:
            try:
                # Never clean up during the stopped-Framework interval.
                require(value("getprop sys.boot_completed") == "1" and
                        re.fullmatch(r"\d+(?:\s+\d+)*", value("pidof system_server")),
                        "leave staging intact until Android is healthy")
                no_guest()
                sh(f"rm -rf {remote}")
            except (RuntimeError, OSError, subprocess.SubprocessError) as e:
                print(f"Stage retained: {remote}: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--accept-legacy-watchdog-risk", action="store_true",
                    help="same explicit consent as existing 20-second reboot smoke")
    ap.add_argument("--ci-log", type=Path)
    ap.add_argument("--serial")
    ap.add_argument("--adb", default=os.environ.get("ADB", str(Path.home() / "Android/Sdk/platform-tools/adb")))
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if not (args.confirm and args.accept_legacy_watchdog_risk):
        ap.error("live comparison requires explicit existing reboot-smoke consent")
    try:
        run(args)
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as e:
        print(f"FRAMEWORK_CPU_BENCHMARK=STOP: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
