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


CPU_PROBE_SCRIPT = "# Bounded read-only CPU telemetry. Do not gate it on a shell parent PID.\n# The bounded loop and stop handler are independent of USB ADB disconnection.\nCPU_PROBE_LOG=\"$STAGE/gpu-bench/cpu-probe.log\"\n(\n    n=0\n    limit=__CPU_PROBE_LIMIT__\n    echo \"oneios-cpu-probe-start: limit=$limit interval_s=5\"\n    while [ \"$n\" -lt \"$limit\" ]; do\n        n=$((n + 1))\n        uptime=$(cut -d' ' -f1 /proc/uptime 2>/dev/null || :)\n        candidates=$(pidof xnuhost-gpu 2>/dev/null || :)\n        pid=\n        for candidate in $candidates; do\n            exe=$(readlink \"/proc/$candidate/exe\" 2>/dev/null || :)\n            if [ \"$exe\" = \"$STAGE/bin/xnuhost-gpu\" ]; then\n                pid=$candidate\n                break\n            fi\n        done\n        if [ -z \"$pid\" ]; then\n            echo \"oneios-cpu-probe-status: sample=$n uptime_s=$uptime state=no_matching_guest candidates=$candidates\"\n        elif [ ! -r \"/proc/$pid/stat\" ]; then\n            echo \"oneios-cpu-probe-status: sample=$n uptime_s=$uptime state=guest_proc_unreadable pid=$pid\"\n        else\n            allowed=$(sed -n 's/^Cpus_allowed_list:[[:space:]]*//p' \"/proc/$pid/status\" 2>/dev/null || :)\n            # /proc/pid/stat has fields 14/15/39 at 12/13/37 after ')'.\n            fields=$(sed 's/^[^)]*) //' \"/proc/$pid/stat\" 2>/dev/null | awk '{print $12, $13, $37}' || :)\n            sched=$(cat \"/proc/$pid/schedstat\" 2>/dev/null || :)\n            mem=$(sed -n 's/^MemAvailable:[[:space:]]*\\([0-9]*\\) kB.*/\\1/p' /proc/meminfo 2>/dev/null || :)\n            psi=$(sed -n 's/^some avg10=\\([^ ]*\\).*/\\1/p' /proc/pressure/cpu 2>/dev/null || :)\n            echo \"oneios-cpu-probe: uptime_s=$uptime pid=$pid allowed=$allowed proc_ticks=$fields schedstat=$sched memavail_kib=$mem cpu_psi_some_avg10=$psi\"\n            for policy in /sys/devices/system/cpu/cpufreq/policy[0-9]*; do\n                [ -d \"$policy\" ] || continue\n                name=$(basename \"$policy\")\n                related=$(cat \"$policy/related_cpus\" 2>/dev/null || :)\n                cur=$(cat \"$policy/scaling_cur_freq\" 2>/dev/null || :)\n                max=$(cat \"$policy/scaling_max_freq\" 2>/dev/null || :)\n                hwmax=$(cat \"$policy/cpuinfo_max_freq\" 2>/dev/null || :)\n                echo \"oneios-cpu-policy: uptime_s=$uptime policy=$name cores=$related cur_khz=$cur max_khz=$max hwmax_khz=$hwmax\"\n            done\n        fi\n        sleep 5\n    done\n    echo \"oneios-cpu-probe-stop: max_samples=$n\"\n) > \"$CPU_PROBE_LOG\" 2>&1 </dev/null &\nCPU_PROBE_PID=$!\necho 'CPU_PROBE_MODE=read_only_5s' >> \"$FAIL\"\n"


def make_visual_script(bench, stage, seconds, ram_mib, touch=False, gpu_trace=True, cpu_probe=False, cpu_affinity_bench=False, frame_trace=False):
    """Reuse the hardened one-shot guest checks and optionally grab ONLY sec_touchscreen."""
    bench.stage_name(stage)
    script = bench.device_run_script(
        stage, seconds, ram_mib, retry_preboot=False,
        max_duration_seconds=bench.VISUAL_DURATION_MAX_SECONDS,
    )
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
    if cpu_affinity_bench:
        if not touch:
            raise ValueError("cpu-affinity-bench requires exclusive physical touch")
        # Opt-in only: four vCPUs paired to four distinct allowed host cores,
        # with per-thread affinity only. The native config rejects all other
        # modes; keep all bridge, Data clone, timeout and takeover gates.
        script = ensure_one(
            script, "    --set bridges=0 \\\n",
            "    --set bridges=0 --set cpu-affinity-bench=1 \\\n",
        )
        script = ensure_one(
            script,
            "echo 'GPU_ADDON=existing_signed_and_trusted' >> \"$FAIL\"\n",
            "echo 'GPU_ADDON=existing_signed_and_trusted' >> \"$FAIL\"\n"
            "echo 'CPU_AFFINITY_BENCH=ON' >> \"$FAIL\"\n",
        )
    # A/B experiment: disabling verbose per-command GPU tracing does NOT
    # disable periodic fence, vCPU, memory, or display performance reports.
    # The xnuhost trace flag is getenv()!=NULL: merely setting it to "0"
    # would still ENABLE tracing. Remove the environment variable entirely.
    if not gpu_trace:
        script = ensure_one(script,
                            "ONEIOS_GPU_TRACE=1 timeout -s TERM -k 15 ",
                            "unset ONEIOS_GPU_TRACE\ntimeout -s TERM -k 15 ")
        script = ensure_one(script,
                            "echo 'GPU_ADDON=existing_signed_and_trusted' >> \"$FAIL\"\n",
                            "echo 'GPU_ADDON=existing_signed_and_trusted' >> \"$FAIL\"\n"
                            "echo 'GPU_TRACE_MODE=off_for_ab' >> \"$FAIL\"\n")
    if frame_trace:
        # Do not silently use 2D for a GPU performance experiment.
        script = ensure_one(script, "--gpu auto --display shm", "--gpu 3d --display shm")
        script = ensure_one(script, "echo 'GPU_MODE=auto' >> \"$FAIL\"\n",
                            "echo 'GPU_MODE=3d' >> \"$FAIL\"\n"
                            "echo 'FRAME_TRACE=1' >> \"$FAIL\"\n")
        script = ensure_one(script, "    --width 1080 --height 2340 --hz 60 \\\n",
                            "    --width 1080 --height 2340 --hz 60 \\\n"
                            "    --set frame-trace=1 \\\n")
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
    if cpu_probe:
        sampler = CPU_PROBE_SCRIPT.replace("__CPU_PROBE_LIMIT__", str(seconds // 5 + 18))
        script = ensure_one(
            script,
            "# The device-side timeout remains active even if USB/SSH disconnects.\n",
            sampler + "# The device-side timeout remains active even if USB/SSH disconnects.\n",
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
    if cpu_probe:
        script = ensure_one(
            script,
            "echo 'VISUAL_HELPER_STOP_REQUESTED=yes' >> \"$FAIL\"\n",
            "echo 'VISUAL_HELPER_STOP_REQUESTED=yes' >> \"$FAIL\"\n"
            "kill \"$CPU_PROBE_PID\" 2>/dev/null || :\n"
            "wait \"$CPU_PROBE_PID\" 2>/dev/null || :\n",
        )
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


def can_detach(state, *, touch, touch_seen, frame_seen, fence_seen):
    """Only hand off a confirmed live GPU guest with its visible input ready."""
    return (state == "running" and frame_seen and fence_seen and
            (not touch or touch_seen))


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
    if report.get("compact_clone_requested"):
        cmd.append("--compact")
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
    cpu_log, cpu_err = get(logbase + "/cpu-probe.log", limit=256 << 10)
    if report.get("action") == "collect":
        # Derive this from the original on-device log, not collect's CLI flags.
        report["touch_requested"] = "VISUAL_MODE=shm_touch_exclusive" in run_log
    artifact_out = ROOT / "out/sm8850/gpu-acceptance"
    artifact_out.mkdir(parents=True, exist_ok=True)
    stamp = report["tag"]
    for name, content in (("xnuhost", host_log), ("display", display_log), ("run", run_log),
                          ("cpu-probe", cpu_log)):
        (artifact_out / (stamp + "-visual-" + name + ".log")).write_text(content)
    report["log_warnings"] = {"xnuhost": host_err, "display": display_err, "run": run_err,
                              "cpu-probe": cpu_err}
    report["cpu_probe"] = {
        "enabled": "CPU_PROBE_MODE=read_only_5s" in run_log,
        "samples": sum(line.startswith("oneios-cpu-probe: ") for line in cpu_log.splitlines()),
        "policy_samples": sum(line.startswith("oneios-cpu-policy: ") for line in cpu_log.splitlines()),
        "log": str(artifact_out / (stamp + "-visual-cpu-probe.log")),
        "started": "oneios-cpu-probe-start:" in cpu_log,
        "diagnostic_windows": sum(line.startswith("oneios-cpu-probe-status: ") for line in cpu_log.splitlines()),
        "valid": ("CPU_PROBE_MODE=read_only_5s" in run_log and
                  any(line.startswith("oneios-cpu-probe: ") for line in cpu_log.splitlines()) and
                  any(re.search(r"cur_khz=[0-9]+", line)
                      for line in cpu_log.splitlines()
                      if line.startswith("oneios-cpu-policy: "))),
    }
    print("CPU_PROBE_VALID=" + str(report["cpu_probe"]["valid"]))
    if report["cpu_probe"]["enabled"] and not report["cpu_probe"]["valid"]:
        print("CPU_PROBE_WARNING=No usable CPU clock/scheduler samples; inspect CPU_PROBE_LOG; do not infer CPU underutilization")
        print("CPU_PROBE_READ_ERROR=" + str(cpu_err))
        for diagnostic in [l for l in cpu_log.splitlines()
                           if l.startswith("oneios-cpu-probe-status: ")][:5]:
            print("CPU_PROBE_DIAGNOSTIC=" + diagnostic)
    print("CPU_PROBE_ENABLED=" + str(report["cpu_probe"]["enabled"]))
    print("CPU_PROBE_SAMPLES=" + str(report["cpu_probe"]["samples"]))
    print("CPU_PROBE_POLICY_SAMPLES=" + str(report["cpu_probe"]["policy_samples"]))
    if report["cpu_probe"]["enabled"]:
        print("CPU_PROBE_LOG=" + report["cpu_probe"]["log"])
    report["cpu_affinity_bench"] = "CPU_AFFINITY_BENCH=ON" in run_log
    print("CPU_AFFINITY_BENCH=" + str(report["cpu_affinity_bench"]))
    report["device_run_log"] = run_log
    report["gpu_trace_mode"] = "OFF_AB" if "GPU_TRACE_MODE=off_for_ab" in run_log else "DEFAULT_ON"
    report["frame_trace_requested_on_device"] = "FRAME_TRACE=1" in run_log
    print("FRAME_TRACE_REQUESTED=" + str(report["frame_trace_requested_on_device"]))
    report["display"] = preview_summary(display_log)
    report["markers"] = bench.summarize_log(host_log)
    # Analyze the *complete* guest and display logs together. The display
    # helper now reports five-second lock/copy/post timing windows. This is
    # host-only parsing; no new guest boot or Android mutation is needed.
    perf = load_tool("sm8850-ios-interactive-perf.py", "oneios_visual_perf")
    report["performance"] = perf.analyze_logs(host_log, display_log)
    print("===== INTERACTIVE IOS PERFORMANCE =====")
    perf._show(report["performance"])
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
    gpu_trace = not bool(getattr(args, "no_gpu_trace", False))
    cpu_probe = bool(getattr(args, "cpu_probe", False))
    frame_trace = bool(getattr(args, "frame_trace", False))
    report["frame_trace_requested"] = frame_trace
    report["compact_clone_requested"] = bool(getattr(args, "compact_clone", False))
    cpu_affinity_bench = bool(getattr(args, "cpu_affinity_bench", False))
    if cpu_affinity_bench and not touch:
        raise ValueError("cpu-affinity-bench requires --touch")
    report["cpu_affinity_bench_requested"] = cpu_affinity_bench
    report["gpu_trace_detailed"] = gpu_trace
    report["cpu_probe_requested"] = cpu_probe
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
        script = make_visual_script(bench, stage, args.duration, args.ram_mib,
                                    touch=touch, gpu_trace=gpu_trace, cpu_probe=cpu_probe,
                                    cpu_affinity_bench=cpu_affinity_bench, frame_trace=frame_trace)
        install = ("cat > '%s/bin/run-visual.sh' <<'ONEIOS_VISUAL_RUN_EOF'\n" % stage
                   + script + "\nONEIOS_VISUAL_RUN_EOF\nchmod 700 '%s/bin/run-visual.sh'\n" % stage)
        harness.root(adb, install, seconds=30)
        launch = ("set -eu\nnohup sh '%s/bin/run-visual.sh' > '%s/gpu-bench/device-run.log' "
                  "2>&1 < /dev/null &\necho VISUAL_RUN_PID=$!\n") % (stage, stage)
        acknowledgment = harness.root(adb, launch, seconds=25).stdout
        if "VISUAL_RUN_PID=" not in acknowledgment:
            raise RuntimeError("device-side visual runner was not acknowledged")
        report["device_launch_acknowledged"] = True
        print("LIVE_VIEW=CHECK_PHONE_SCREEN_NOW", flush=True)
        if touch:
            print("TOUCH_PREVIEW=WAIT_FOR_LIVE_TOUCH_GRABBED_BEFORE_SWIPING", flush=True)
        print("VISUAL_SESSION_LIMIT=%d_seconds; NO_TAKEOVER=yes" % args.duration, flush=True)
        print("GPU_DETAILED_TRACE=" + ("ON_BASELINE" if gpu_trace else "OFF_AB_EXPERIMENT"), flush=True)
        print("FRAME_TRACE=" + ("ON" if frame_trace else "OFF"), flush=True)
        print("CPU_READONLY_PROBE=" + ("ON_5S" if cpu_probe else "OFF"), flush=True)
        print("CPU_CORE_PAIRING=" + ("ON_EXPERIMENT" if cpu_affinity_bench else "OFF_BASELINE"), flush=True)
        deadline = time.monotonic() + args.duration + 210
        state, frame_seen, fence_seen = "pending", False, False
        touch_seen = False
        detached = False
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
            if getattr(args, "detach", False) and can_detach(
                state, touch=touch, touch_seen=touch_seen,
                frame_seen=frame_seen, fence_seen=fence_seen
            ):
                # The device-side runner owns its TERM/KILL timeout.
                # Only the host ADB polling/collection ends here.
                detached = True
                break
            time.sleep(5)
        report["polled_state"] = state
        if detached:
            report["collection_status"] = "DEFERRED_UNTIL_RECONNECT"
            report["detached"] = True
            report["device_timeout_seconds"] = args.duration
        else:
            acquire_evidence(harness, adb, stage, report, bench)
            print("VISUAL_BENCH_FINISHED=YES", flush=True)
    finally:
        # Only remove uploads with this run's exact nonce; never delete a snapshot.
        # The fully staged binaries are independent of these incoming copies.
        try:
            harness.root(adb, "rm -f " + " ".join("'%s'" % p for p in uploads.values()), seconds=20)
        except Exception as exc:
            report["upload_cleanup_warning"] = str(exc)
    if detached:
        # Print only AFTER cleanup. The owner may now safely disconnect USB.
        print("DETACH_READY=YES; SAFE_TO_UNPLUG_USB=YES", flush=True)
        print("COLLECT_AFTER_RECONNECT_STAGE=" + stage, flush=True)
        print("PHONE_SIDE_TIMEOUT_SECONDS=" + str(args.duration), flush=True)


def collect_finished(args, report):
    """Read-only evidence recovery for a consumed, finished, detached session."""
    bench = load_tool("sm8850-ios-gpu-bench.py", "oneios_collect_bench")
    harness = load_tool("sm8850-gpu-acceptance.py", "oneios_collect_acceptance")
    stage = bench.stage_name(args.stage)  # exact /data/adb/..16-hex nonce
    adb = harness.select_usb(args.adb, args.serial)
    report["serial"] = adb[-1]
    report["stage"] = stage
    # Refuse collection while an active guest might be writing the logs.
    # No guest launch, snapshot, chown, sysctl, takeover or stop operation.
    required = (stage + "/gpu-bench/attempted", stage + "/gpu-bench/launch.claim",
                stage + "/source-verified.sha256.txt")
    checks = " && ".join("[ %s '%s' ]" % ("-d" if p.endswith("launch.claim") else "-f", p) +
                       " && [ ! -L '%s' ]" % p for p in required)
    evidence = harness.root(adb, "if " + checks + "; then echo COLLECT_STAGE=VERIFIED; "
                            "else echo COLLECT_STAGE=INVALID; fi", seconds=20).stdout.strip()
    if evidence != "COLLECT_STAGE=VERIFIED":
        raise RuntimeError("collect requires a previously attempted exact private snapshot stage")
    state = harness.root(adb,
                         "cat '%s/gpu-bench/state' 2>/dev/null || echo missing" % stage,
                         seconds=20).stdout.strip()
    if not re.fullmatch(r"finished:[0-9]+", state):
        raise RuntimeError("guest not confirmed finished; leave iOS running, reconnect later; state=" + state[:80])
    report["collection_status"] = "POST_RUN_READ_ONLY"
    print("COLLECT_SOURCE_STAGE=" + stage, flush=True)
    acquire_evidence(harness, adb, stage, report, bench)
    print("COLLECT_COMPLETE=YES", flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("run", "collect"))
    p.add_argument("--duration", type=int, default=240, help="guest lifetime in seconds (90..1800; default 240), strictly bounded on device")
    p.add_argument("--touch", action="store_true", help="bench-only exclusive native sec_touchscreen to iOS; physical Android touch suspended")
    p.add_argument("--detach", action="store_true", help="return after live guest GPU/display/touch are confirmed; collect logs after USB reconnect")
    p.add_argument("--no-gpu-trace", action="store_true", help="run only: suppress verbose GPU command trace for A/B without disabling performance/fence logging")
    p.add_argument("--compact-clone", action="store_true", help="run only: measure sparse Data payload before allocating; keep 30 GiB reserve and copy margin")
    p.add_argument("--frame-trace", action="store_true", help="run only: require GPU3D and enable bounded host frame, fence and queue stage telemetry")
    p.add_argument("--cpu-probe", action="store_true", help="run only: read-only 5s CPU frequency, allowed cores and runqueue telemetry for detach/collect")
    p.add_argument("--cpu-affinity-bench", action="store_true", help="run only: opt-in native per-vCPU/iOS-thread pairing to four distinct allowed cores; no boosts or full bridges")
    p.add_argument("--stage", help="collect only: exact private snapshot path printed by run --detach")
    p.add_argument("--ram-mib", type=int, default=4096)
    p.add_argument("--serial")
    p.add_argument("--adb", default=shutil.which("adb") or str(Path.home() / "Android/Sdk/platform-tools/adb"))
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    if args.action == "run":
        if args.stage:
            p.error("--stage is only accepted for collect; run always makes a fresh Data clone")
        if args.cpu_affinity_bench and not args.touch:
            p.error("--cpu-affinity-bench requires --touch")
        if not 90 <= args.duration <= load_tool("sm8850-ios-gpu-bench.py", "oneios_visual_duration").VISUAL_DURATION_MAX_SECONDS or args.ram_mib not in range(2048, 5121, 256):
            p.error("duration must be 90..1800 seconds, RAM 2048..5120 MiB in 256 MiB steps")
    else:
        if not args.stage or args.detach or args.touch or args.no_gpu_trace or args.cpu_probe or args.cpu_affinity_bench or args.frame_trace or args.compact_clone:
            p.error("collect requires --stage and cannot launch or detach a guest")
        try:
            load_tool("sm8850-ios-gpu-bench.py", "oneios_collect_validate").stage_name(args.stage)
        except ValueError as exc:
            p.error(str(exc))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.output or ROOT / "out/sm8850/gpu-acceptance" / (stamp + "-ios-gpu-visual.json")
    report = {"tag": stamp, "action": args.action,
              "duration_seconds": args.duration if args.action == "run" else None,
              "IOS_VULKAN": "UNVERIFIED", "FRAMEWORK_TAKEOVER": "BLOCKED",
              "scope": "one-shot visible SHM guest; no takeover; bounded phone-side timeout",
              "touch_requested": args.touch if args.action == "run" else None}
    rc = 0
    try:
        if args.action == "run":
            run_visible(args, report)
        else:
            collect_finished(args, report)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        rc = 2
        report["error"] = str(exc)
        print("VISUAL_BENCH_ERROR=" + str(exc), file=sys.stderr, flush=True)
        if args.action == "run" and report.get("device_launch_acknowledged"):
            print("DEVICE_SESSION_MAY_STILL_BE_RUNNING=YES; DO_NOT_RETRY_OR_REUSE_STAGE", file=sys.stderr, flush=True)
            print("COLLECT_AFTER_RECONNECT_STAGE=" + report["stage"], file=sys.stderr, flush=True)
    finally:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("REPORT=" + str(out), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
