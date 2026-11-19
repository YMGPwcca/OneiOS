#!/usr/bin/env python3
"""One-shot visible iOS GPU demo on S26 Ultra, without Framework takeover.

Build host + display artifacts, clone verified original APFS Data to a fresh
root-private candidate, launch a bounded guest with a temporary SurfaceFlinger
layer and collect guest GPU + actual display-post evidence. Never reuse a
consumed Data clone. The owner visually confirms the panel's iOS content.
"""

import argparse
import hashlib
import importlib.util
import json
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MIN_MAP_COUNT = 1048576
MAX_LOG_BYTES = 64 << 20
DISPLAY_ARTIFACTS = (
    "oneios-display",
    "liboneios-display.so",
    "oneios-display.dex",
)


def load_tool(name, module_name):
    path = HERE / name
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("missing OneiOS tool: " + str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_one(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("visual runner cannot safely transform current bench script: " + old[:70])
    return text.replace(old, new, 1)


def make_visual_script(bench, stage, seconds, ram_mib, touch=False):
    """Reuse the hardened one-shot guest checks and optionally grab ONLY sec_touchscreen."""
    bench.stage_name(stage)
    script = bench.device_run_script(stage, seconds, ram_mib, retry_preboot=False)
    script = ensure_one(
        script,
        "    --gpu auto --display none --no-input \\\n",
        "    --gpu auto --display shm --no-input \\\n",
    )
    if touch:
        # Never feed touches to One UI underneath the visible iOS layer.
        # Native xnuhost must EVIOCGRAB sec_touchscreen or refuse to boot.
        script = ensure_one(
            script,
            "    --gpu auto --display shm --no-input \\\n",
            "    --gpu auto --display shm --set touch-exclusive=1 \\\n",
        )
    # The old runner's session, snapshot hash, and attempted marker remain.
    gate = '''# No untracked global sysctl change is permitted for this demo.
# xnuhost's xh_mem_map_limit() raises this kernel-wide limit when too low.
CURRENT_MAP_COUNT=$(cat /proc/sys/vm/max_map_count) || exit 2
case "$CURRENT_MAP_COUNT" in *[!0-9]*|'') echo 'ERROR=invalid_map_count' >> "$FAIL"; exit 2 ;; esac
if [ "$CURRENT_MAP_COUNT" -lt 1048576 ]; then
    echo 'ERROR=map_count_below_required_for_nonmutating_guest' >> "$FAIL"
    printf 'blocked\n' > "$STATUS"
    exit 2
fi
'''
    script = ensure_one(
        script,
        "# Mark the candidate as consumed before its first writable guest open.\n",
        gate + "# Mark the candidate as consumed before its first writable guest open.\n",
    )
    start = '''# Show the existing guest framebuffer through SurfaceFlinger; no --takeover.
# --socket has no guest-ready hold, so the owner can see early boot output.
# A separate device-side deadline removes the layer even if the host disconnects.
VISUAL_LOG="$STAGE/gpu-bench/display.log"
echo 'VISUAL_MODE=shm_no_takeover' >> "$FAIL"
timeout -s TERM -k 10 __VIEW_DEADLINE__ "$STAGE/bin/oneios-display" \\
    --socket "$STAGE/gpu-bench/session/display.sock" --wait 65 \\
    > "$VISUAL_LOG" 2>&1 < /dev/null &
VISUAL_PID=$!
printf 'VISUAL_PID=%s\\n' "$VISUAL_PID" >> "$FAIL"
'''.replace("__VIEW_DEADLINE__", str(seconds + 45))
    if touch:
        start = start.replace("VISUAL_MODE=shm_no_takeover", "VISUAL_MODE=shm_touch_exclusive")
    script = ensure_one(
        script,
        "# The device-side timeout remains active even if USB/SSH disconnects.\n",
        start + "# The device-side timeout remains active even if USB/SSH disconnects.\n",
    )
    stop = '''# The guest socket closing normally makes the display helper remove its layer.
# Ask it to exit as well; the separate timeout above is a final backstop.
if kill -0 "$VISUAL_PID" 2>/dev/null; then
    kill "$VISUAL_PID" 2>/dev/null || :
fi
wait "$VISUAL_PID" 2>/dev/null || :
echo 'VISUAL_HELPER_STOP_REQUESTED=yes' >> "$FAIL"
'''
    script = ensure_one(script, "rc=$?\nprintf 'GUEST_EXIT=", "rc=$?\n" + stop + "printf 'GUEST_EXIT=")
    if "--takeover" in script.replace("# Show the existing guest framebuffer through SurfaceFlinger; no --takeover.", ""):
        raise RuntimeError("takeover flag unexpectedly present in visual script")
    return script


def prepare_display_shell(stage, nonce, artifact_digests):
    if not re.fullmatch(r"/data/adb/oneios-m3q-gpu-snapshot-[0-9a-f]{16}", stage):
        raise ValueError("invalid private snapshot stage path")
    if not re.fullmatch(r"[0-9a-f]{16}", nonce):
        raise ValueError("bad upload nonce")
    for name in DISPLAY_ARTIFACTS:
        if not re.fullmatch(r"[0-9a-f]{64}", artifact_digests.get(name, "")):
            raise ValueError("missing validated display artifact SHA-256")
    specs = []
    for name in DISPLAY_ARTIFACTS:
        up = "/data/local/tmp/oneios-visual-%s-%s" % (nonce, name)
        spec = (
            "[ -f '{up}' ] && [ ! -L '{up}' ] || fail 'display artifact missing: {name}'\n"
            "[ \"$(sha256sum '{up}' | cut -d ' ' -f1)\" = '{sha}' ] || fail 'display upload hash: {name}'\n"
            "[ ! -e \"$STAGE/bin/{name}\" ] || fail 'display already staged: {name}'\n"
            "cp '{up}' \"$STAGE/bin/{name}\"\n"
            "chmod {mode} \"$STAGE/bin/{name}\"\n"
            "[ \"$(sha256sum \"$STAGE/bin/{name}\" | cut -d ' ' -f1)\" = '{sha}' ] || fail 'display staged hash: {name}'"
        ).format(up=up, name=name, sha=artifact_digests[name], mode="700" if name == "oneios-display" else "400")
        specs.append(spec)
    return "set -eu\numask 077\nSTAGE='%s'\nfail() { echo \"VISUAL_STAGE_BLOCKED=$*\" >&2; exit 2; }\n%s\necho VISUAL_ARTIFACTS=PASS\n" % (stage, "\n".join(specs))


def preview_summary(display_log):
    first = "first frame posted" in display_log
    frame_counts = [int(v) for v in re.findall(r"socket closed after (\d+) frames", display_log)]
    return {
        "first_frame_posted": first,
        "reported_closed_frame_count": max(frame_counts, default=None),
        "display_errors": [line.strip() for line in display_log.splitlines()
                           if re.search(r"exception|failed|fatal|missing|error", line, re.IGNORECASE)][-20:],
    }


def checked_build():
    targets = [
        ["make", "-C", str(ROOT / "runtime/xnuhost"), "-j8", "build/android/xnuhost"],
        ["make", "-C", str(ROOT / "runtime/display"), "-j8", "all"],
    ]
    for cmd in targets:
        print("BUILD=" + " ".join(cmd), flush=True)
        subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL, timeout=600)


def verified_local_artifacts():
    files = {"xnuhost": ROOT / "runtime/xnuhost/build/android/xnuhost"}
    for name in DISPLAY_ARTIFACTS:
        files[name] = ROOT / "runtime/display/build/android" / name
    for name, path in files.items():
        if not path.is_file() or path.is_symlink() or path.stat().st_size < 256:
            raise RuntimeError("missing or invalid built artifact: " + str(path))
    if b"vgpu-3d=1" not in files["xnuhost"].read_bytes():
        raise RuntimeError("xnuhost binary does not include the vgpu-3d fix")
    return files, {name: digest(path) for name, path in files.items()}


def snapshot_new(adb, harness, report):
    cmd = [sys.executable, str(HERE / "sm8850-gpu-data-snapshot.py"),
           "snapshot", "--serial", adb[-1], "--adb", adb[0]]
    print("SNAPSHOT_NEW_DATA=STARTED (original Data is read-only)", flush=True)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL, text=True, timeout=1800)
    print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n", flush=True)
    if proc.returncode or proc.stdout.count("DATA_CLONE_READY=PASS") != 1:
        raise RuntimeError("guarded APFS Data snapshot failed; no iOS guest started")
    matches = re.findall(r"^STAGE_PATH=(.*)$", proc.stdout, re.MULTILINE)
    if len(matches) != 1:
        raise RuntimeError("snapshot reported an ambiguous private stage path")
    stage = matches[0].strip()
    load_tool("sm8850-ios-gpu-bench.py", "oneios_bench_snapshot").stage_name(stage)
    report["stage"] = stage
    return stage


def push_file(adb, path, remote):
    proc = subprocess.run([*adb, "push", str(path), remote],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL, text=True, timeout=120)
    if proc.returncode:
        raise RuntimeError("ADB upload failed for " + path.name + ": " + proc.stdout[-1200:])


def acquire_evidence(harness, adb, stage, report, bench):
    logbase = stage + "/gpu-bench"
    state = harness.root(adb, "cat '%s/state' 2>/dev/null || echo missing" % logbase, seconds=20).stdout.strip()
    report["remote_state"] = state
    def get(remote, limit=MAX_LOG_BYTES):
        stat = harness.root(adb, "stat -c '%%s' '%s' 2>/dev/null || echo 0" % remote, seconds=20).stdout.strip()
        if not stat.isdigit() or int(stat) > limit:
            return "", "file missing or exceeds collection cap"
        if int(stat) == 0:
            return "", "empty or missing"
        return harness.root(adb, "cat '%s'" % remote, seconds=120).stdout, None
    host_log, host_err = get(logbase + "/xnuhost.log")
    display_log, display_err = get(logbase + "/display.log", limit=2 << 20)
    run_log, run_err = get(logbase + "/run.log", limit=1 << 20)
    artifact_out = ROOT / "out/sm8850/gpu-acceptance"
    artifact_out.mkdir(parents=True, exist_ok=True)
    stamp = report["tag"]
    for name, content in (("xnuhost", host_log), ("display", display_log), ("run", run_log)):
        (artifact_out / (stamp + "-visual-" + name + ".log")).write_text(content)
    report["log_warnings"] = {"xnuhost": host_err, "display": display_err, "run": run_err}
    report["device_run_log"] = run_log
    report["display"] = preview_summary(display_log)
    report["markers"] = bench.summarize_log(host_log)
    marks = report["markers"]
    report["GUEST_GPU_PATH"] = "OBSERVED" if marks["gpu_execution_observed"] else "UNVERIFIED"
    report["IOS_VULKAN"] = "UNVERIFIED"  # No vkCreateDevice instrumented guest yet.
    report["touch"] = {
        "requested": bool(report.get("touch_requested", False)),
        "grabbed": "input: touch-exclusive: sec_touchscreen grabbed" in host_log,
        "gestures_logged": len(re.findall(r"input: touch: [0-9]+ frame", host_log)),
        "release_logged": "input: touch-exclusive: sec_touchscreen released" in host_log,
    }
    print("TOUCH_EXCLUSIVE_GRABBED=" + str(report["touch"]["grabbed"]))
    print("TOUCH_GESTURES_LOGGED=" + str(report["touch"]["gestures_logged"]))
    print("TOUCH_RELEASE_LOGGED=" + str(report["touch"]["release_logged"]))
    print("DEVICE_BENCH_STATE=" + state)
    print("DISPLAY_FIRST_FRAME=" + str(report["display"]["first_frame_posted"]))
    print("DISPLAY_FRAMES_POSTED=" + str(report["display"]["reported_closed_frame_count"]))
    print("GPU_BOOTARGS_VGPU3D=" + str(marks["bootargs_vgpu_3d"]))
    print("GPU_DRM_NATIVE=" + str(marks["gpu_drm_native"]))
    print("GPU_FENCES_REPORTED_TOTAL=" + str(marks.get("backboardd_fences_reported_total", "see log")))
    print("GPU_FENCES_MAX=" + str(marks["backboardd_fences_max"]))
    print("VK_ERROR_MINUS3=" + str(marks["legacy_vulkan_failure"]))
    print("QUARTZCORE_ABORT=" + str(marks["quartzcore_abort"]))
    print("GUEST_GPU_PATH=" + report["GUEST_GPU_PATH"])
    print("IOS_VULKAN=UNVERIFIED (no direct vkCreateDevice trace)")
    if run_log:
        print("DEVICE_RUN_LOG_BEGIN\n" + run_log[-5000:] + "\nDEVICE_RUN_LOG_END")
    if display_log:
        print("DISPLAY_LOG_TAIL_BEGIN\n" + "\n".join(display_log.splitlines()[-24:]) + "\nDISPLAY_LOG_TAIL_END")
    if not state.startswith("finished:"):
        raise RuntimeError("device-side visual bench was blocked or did not finish; inspect saved logs")
    if not host_log.strip():
        raise RuntimeError("guest was not logged; inspect saved logs")
    if report["touch"]["requested"] and not report["touch"]["grabbed"]:
        raise RuntimeError("exclusive sec_touchscreen grab was never confirmed in guest log")


def run_visible(args, report):
    harness = load_tool("sm8850-gpu-acceptance.py", "oneios_visual_acceptance")
    bench = load_tool("sm8850-ios-gpu-bench.py", "oneios_visual_bench")
    checked_build()                  # Before making a new Data clone.
    files, hashes = verified_local_artifacts()
    touch = bool(getattr(args, "touch", False))
    report["touch_requested"] = touch
    if touch and b"touch-exclusive=1 requires" not in files["xnuhost"].read_bytes():
        raise RuntimeError("xnuhost binary lacks the bench-only touchscreen grab guard; rebuild failed")
    report["artifact_sha256"] = hashes
    adb = harness.select_usb(args.adb, args.serial)
    report["serial"] = adb[-1]
    values = harness.decode_kv(harness.root(adb, harness.DEVICE_AUDIT).stdout)
    checks, failures = harness.validate_preflight(values)
    report["preflight"] = {"checks": checks, "failures": failures}
    if failures:
        raise RuntimeError("device preflight blocked: " + ", ".join(failures))
    # The first bench already raised this global knob; do not make it mutate again.
    map_count = values.get("map_count", "")
    if not map_count.isdigit() or int(map_count) < MIN_MAP_COUNT:
        raise RuntimeError("map_count below 1048576; xnuhost would change a shared sysctl. No guest launched")
    print("PREFLIGHT=PASS\nMAP_COUNT_MUTATION=GUARDED", flush=True)
    stage = snapshot_new(adb, harness, report)
    incoming_nonce = secrets.token_hex(8)
    host_incoming, setup = bench.safe_shell(stage, hashes["xnuhost"], incoming_nonce)
    uploads = {"xnuhost": host_incoming}
    uploads.update({name: "/data/local/tmp/oneios-visual-%s-%s" % (incoming_nonce, name)
                    for name in DISPLAY_ARTIFACTS})
    try:
        for name, up in uploads.items():
            push_file(adb, files[name], up)
        prep = harness.root(adb, setup, seconds=90)
        if "PREPARED=PASS" not in prep.stdout:
            raise RuntimeError("xnuhost private staging did not acknowledge success")
        display_setup = prepare_display_shell(stage, incoming_nonce, hashes)
        disp = harness.root(adb, display_setup, seconds=90)
        if "VISUAL_ARTIFACTS=PASS" not in disp.stdout:
            raise RuntimeError("display helper private staging did not acknowledge success")
        script = make_visual_script(bench, stage, args.duration, args.ram_mib, touch=touch)
        install = ("cat > '%s/bin/run-visual.sh' <<'ONEIOS_VISUAL_RUN_EOF'\n" % stage
                   + script + "\nONEIOS_VISUAL_RUN_EOF\nchmod 700 '%s/bin/run-visual.sh'\n" % stage)
        harness.root(adb, install, seconds=30)
        launch = ("set -eu\nnohup sh '%s/bin/run-visual.sh' > '%s/gpu-bench/device-run.log' "
                  "2>&1 < /dev/null &\necho VISUAL_RUN_PID=$!\n") % (stage, stage)
        acknowledgment = harness.root(adb, launch, seconds=25).stdout
        if "VISUAL_RUN_PID=" not in acknowledgment:
            raise RuntimeError("device-side visual runner was not acknowledged")
        print("LIVE_VIEW=CHECK_PHONE_SCREEN_NOW", flush=True)
        if touch:
            print("TOUCH_PREVIEW=WAIT_FOR_LIVE_TOUCH_GRABBED_BEFORE_SWIPING", flush=True)
        print("VISUAL_SESSION_LIMIT=%d_seconds; NO_TAKEOVER=yes" % args.duration, flush=True)
        deadline = time.monotonic() + args.duration + 210
        state, frame_seen, fence_seen = "pending", False, False
        touch_seen = False
        while time.monotonic() < deadline:
            p = harness.root(adb, "cat '%s/gpu-bench/state' 2>/dev/null || echo pending" % stage,
                             seconds=18).stdout.strip()
            state = p.splitlines()[-1] if p else "pending"
            if touch and not touch_seen:
                grabbed = harness.root(
                    adb,
                    "grep -m 1 -F 'input: touch-exclusive: sec_touchscreen grabbed' '%s/gpu-bench/xnuhost.log' 2>/dev/null || :" % stage,
                    seconds=18,
                ).stdout
                if "input: touch-exclusive: sec_touchscreen grabbed" in grabbed:
                    touch_seen = True
                    print("LIVE_TOUCH_GRABBED=YES; TOUCH_IOS_ON_PHONE_NOW", flush=True)
            if not frame_seen:
                posted = harness.root(adb, "grep -m 1 -F 'first frame posted' '%s/gpu-bench/display.log' 2>/dev/null || :" % stage,
                                      seconds=18).stdout
                if "first frame posted" in posted:
                    frame_seen = True
                    print("LIVE_DISPLAY_FIRST_FRAME=POSTED", flush=True)
                    print("VIEW_PHONE=The iOS framebuffer is now on the display layer", flush=True)
            if not fence_seen:
                hit = harness.root(adb,
                                   "grep -m 1 -E 'backboardd fences [1-9][0-9]*' '%s/gpu-bench/xnuhost.log' 2>/dev/null || :" % stage,
                                   seconds=18).stdout
                if re.search(r"backboardd fences [1-9][0-9]*", hit):
                    fence_seen = True
                    print("LIVE_ADRENO_FENCES=OBSERVED", flush=True)
            if state.startswith("finished:") or state.startswith("blocked"):
                break
            time.sleep(5)
        report["polled_state"] = state
        acquire_evidence(harness, adb, stage, report, bench)
        print("VISUAL_BENCH_FINISHED=YES", flush=True)
    finally:
        # Only remove uploads with this run's exact nonce; never delete a snapshot.
        try:
            harness.root(adb, "rm -f " + " ".join("'%s'" % p for p in uploads.values()), seconds=20)
        except Exception as exc:
            report["upload_cleanup_warning"] = str(exc)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("run",))
    p.add_argument("--duration", type=int, default=240)
    p.add_argument("--touch", action="store_true", help="bench-only exclusive native sec_touchscreen to iOS; physical Android touch suspended")
    p.add_argument("--ram-mib", type=int, default=4096)
    p.add_argument("--serial")
    p.add_argument("--adb", default=shutil.which("adb") or str(Path.home() / "Android/Sdk/platform-tools/adb"))
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    if not 90 <= args.duration <= 300 or args.ram_mib not in range(2048, 5121, 256):
        p.error("duration must be 90..300 seconds, RAM 2048..5120 MiB in 256 MiB steps")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output or ROOT / "out/sm8850/gpu-acceptance" / (stamp + "-ios-gpu-visual.json")
    report = {"tag": stamp, "action": args.action, "IOS_VULKAN": "UNVERIFIED",
              "FRAMEWORK_TAKEOVER": "BLOCKED", "scope": "one-shot visible SHM guest; fresh Data clone; no takeover",
              "touch_requested": args.touch}
    rc = 0
    try:
        run_visible(args, report)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        rc = 2
        report["error"] = str(exc)
        print("VISUAL_BENCH_ERROR=" + str(exc), file=sys.stderr, flush=True)
    finally:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("REPORT=" + str(out), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
