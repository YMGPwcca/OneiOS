#!/usr/bin/env python3
"""One-shot, bounded SM8850 iOS GPU bench. One UI stays up; Data clone only.

Keep the existing signed GPU addon, image and trustcache for this first test.
Use a freshly built xnuhost with the corrected vgpu-3d=1 default.
No takeover, physical input, watchdog device, APFS source writes or sysctl changes.
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
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
STAGE_PATTERN = re.compile(r"/data/adb/oneios-m3q-gpu-snapshot-[0-9a-f]{16}\Z")
BENCH = "/data/local/tmp/oneios-m3q-ios27-bench"
DATA_BYTES = 8 * 1024**3
MIN_FREE_KIB = 30 * 1024 * 1024 + 65536

def load_harness():
    path = HERE / "sm8850-gpu-acceptance.py"
    spec = importlib.util.spec_from_file_location("sm8850_gpu", path)
    if spec is None or spec.loader is None:
        raise ValueError("GPU acceptance harness missing")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def stage_name(stage):
    if STAGE_PATTERN.fullmatch(stage) is None:
        raise ValueError("snapshot stage path must be an exact nonce-owned OneiOS snapshot")
    return stage


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for part in iter(lambda: f.read(4 << 20), b""):
            h.update(part)
    return h.hexdigest()


def safe_shell(stage, host_sha, nonce, *, retry_preboot=False):
    stage_name(stage)
    if not re.fullmatch(r"[0-9a-f]{64}", host_sha) or not re.fullmatch(r"[0-9a-f]{16}", nonce):
        raise ValueError("invalid digest or upload nonce")
    incoming = f"/data/local/tmp/oneios-gpu-bench-{nonce}"
    binary = "xnuhost-gpu-retry" if retry_preboot else "xnuhost-gpu"
    if retry_preboot:
        # Never allow a second guest run against a Data clone that might have changed.
        guard = '''
[ ! -e "$STAGE/gpu-bench/attempted" ] || fail 'guest already attempted on this Data clone'
[ -f "$STAGE/gpu-bench/run.log" ] && [ ! -L "$STAGE/gpu-bench/run.log" ] || fail 'missing previous blocker evidence'
[ "$(cat "$STAGE/gpu-bench/state" 2>/dev/null)" = blocked:2 ] || fail 'previous bench was not blocked:2'
grep -Fxq 'ERROR=trusted_addon_missing' "$STAGE/gpu-bench/run.log" || fail 'previous blocker was not trustcache sidecar gate'
[ "$(grep -c '^ERROR=' "$STAGE/gpu-bench/run.log" || :)" = 1 ] || fail 'previous run had ambiguous errors'
[ ! -s "$STAGE/gpu-bench/xnuhost.log" ] || fail 'previous guest log exists: never retry a booted Data clone'
[ ! -e "$STAGE/gpu-bench/retry-preboot" ] && [ ! -L "$STAGE/gpu-bench/retry-preboot" ] || fail 'preboot retry already exists'
[ ! -e "$STAGE/bin/xnuhost-gpu-retry" ] && [ ! -e "$STAGE/bin/run-gpu-retry.sh" ] || fail 'retry executable already exists'
[ "$(stat -c '%u:%a' "$STAGE/gpu-bench")" = 0:700 ] || fail 'previous log directory owner/mode'
mkdir -m 700 "$STAGE/gpu-bench/retry-preboot" || fail 'retry evidence directory cannot be created'
'''
    else:
        guard = '''
[ ! -e "$STAGE/gpu-bench/attempted" ] || fail 'snapshot previously used for a bench'
[ ! -e "$STAGE/bin/xnuhost-gpu" ] && [ ! -e "$STAGE/bin/run-gpu.sh" ] || fail 'stage contains an older GPU runner'
mkdir -m 700 "$STAGE/gpu-bench" || fail 'cannot create gpu-bench directory'
'''
    return incoming, f'''set -eu
umask 077
STAGE='{stage}'
BASE='{BENCH}'
UP='{incoming}'
fail() {{ echo "BENCH_BLOCKED=$*" >&2; exit 2; }}
[ "$(id -u)" = 0 ] || fail 'not root'
[ "$(getprop sys.boot_completed)" = 1 ] || fail 'Android not booted'
[ "$(getprop init.svc.zygote)" = running ] && pidof system_server >/dev/null || fail 'Framework unavailable'
[ "$(getenforce)" = Enforcing ] || fail 'SELinux not enforcing'
[ "$(getprop ro.product.model):$(getprop ro.product.device):$(getprop ro.soc.model)" = SM-S948B:m3q:SM8850 ] || fail 'device mismatch'
[ "$(getprop ro.build.version.incremental)" = S948BXXS4BZIG ] || fail 'firmware mismatch'
[ ! -L "$STAGE" ] && [ "$(stat -c '%u:%a' "$STAGE")" = 0:700 ] || fail 'snapshot owner/mode'
[ ! -L "$STAGE/data" ] && [ "$(stat -c '%u:%a' "$STAGE/data")" = 0:700 ] || fail 'data directory owner/mode'
[ -f "$STAGE/source-verified.sha256.txt" ] || fail 'snapshot hash record missing'
[ ! -L "$STAGE/data/data.img" ] && [ ! -L "$STAGE/data/unique-chip-id" ] || fail 'symlinked snapshot'
[ "$(stat -c '%s:%h' "$STAGE/data/data.img")" = '{DATA_BYTES}:1' ] || fail 'snapshot Data size/hardlinks'
[ "$(stat -c '%s:%h' "$STAGE/data/unique-chip-id")" = '8:1' ] || fail 'snapshot chip size/hardlinks'
[ "$(stat -c '%d:%i' "$BASE/data/data.img")" != "$(stat -c '%d:%i' "$STAGE/data/data.img")" ] || fail 'Data not independent'
[ -f "$UP" ] && [ ! -L "$UP" ] && [ "$(sha256sum "$UP" | cut -d ' ' -f1)" = '{host_sha}' ] || fail 'binary upload hash'
[ "$(df -Pk "$STAGE" | awk 'END {{print $4}}')" -ge {MIN_FREE_KIB} ] || fail '30 GiB reserve'
if pidof xnuhost xnuhost-gui-bench xnuhost-tasks oneios-display OneiOSDisplay >/dev/null 2>&1; then fail 'guest already running'; fi
command -v timeout >/dev/null || fail 'missing device-side timeout'
command -v nohup >/dev/null || fail 'missing nohup; no disconnected execution permitted'
command -v flock >/dev/null || fail 'missing flock'
{guard}
cp "$UP" "$STAGE/bin/{binary}"
chmod 700 "$STAGE/bin/{binary}"
[ "$(sha256sum "$STAGE/bin/{binary}" | cut -d ' ' -f1)" = '{host_sha}' ] || fail 'staged binary hash mismatch'
printf 'XNHOST_SHA256={host_sha}\n' > "$STAGE/gpu-bench/{'retry-preboot/' if retry_preboot else ''}artifact.txt"
echo PREPARED=PASS
'''


def device_run_script(stage, seconds, memory_mib, *, retry_preboot=False):
    stage_name(stage)
    if seconds < 30 or seconds > 300 or memory_mib < 2048 or memory_mib > 5120 or memory_mib % 256:
        raise ValueError("bounded test limits exceeded")
    log_dir = "gpu-bench/retry-preboot" if retry_preboot else "gpu-bench"
    binary = "xnuhost-gpu-retry" if retry_preboot else "xnuhost-gpu"
    return f'''#!/system/bin/sh
set -u
umask 077
STAGE='{stage}'
BASE='{BENCH}'
LOG="$STAGE/{log_dir}/xnuhost.log"
STATUS="$STAGE/{log_dir}/state"
FAIL="$STAGE/{log_dir}/run.log"
finish_state() {{
    code=$?
    value=$(cat "$STATUS" 2>/dev/null || :)
    case "$value" in finished:*|blocked*) ;; *) printf 'blocked:%s\n' "$code" > "$STATUS" ;; esac
}}
trap finish_state EXIT
exec 8>"$STAGE/{log_dir}/launch.lock"
if ! flock -n 8; then echo 'ERROR=locked' >> "$FAIL"; exit 2; fi
printf 'preparing\n' > "$STATUS"
[ "$(id -u)" = 0 ] || exit 2
[ "$(getprop sys.boot_completed)" = 1 ] && [ "$(getprop init.svc.zygote)" = running ] && pidof system_server >/dev/null 2>&1 || exit 2
[ "$(getenforce)" = Enforcing ] || exit 2
if pidof xnuhost xnuhost-gui-bench xnuhost-tasks oneios-display OneiOSDisplay >/dev/null 2>&1; then
    echo 'ERROR=another_guest_running' >> "$FAIL"
    printf 'blocked\n' > "$STATUS"
    exit 2
fi
# Validate both current original and isolated clone against the verified snapshot hashes.
EXPECTED_DATA=$(sed -n 's/^data_sha256=//p' "$STAGE/source-verified.sha256.txt")
EXPECTED_CHIP=$(sed -n 's/^chip_sha256=//p' "$STAGE/source-verified.sha256.txt")
for h in "$EXPECTED_DATA" "$EXPECTED_CHIP"; do
    case "$h" in *[!0-9a-f]*|'') echo 'ERROR=invalid_snapshot_hash' >> "$FAIL"; printf 'blocked\n' > "$STATUS"; exit 2 ;; esac
    [ "${{#h}}" -eq 64 ] || exit 2
done
for p in "$BASE/data/data.img" "$STAGE/data/data.img"; do
    [ ! -L "$p" ] && [ "$(sha256sum "$p" | cut -d ' ' -f1)" = "$EXPECTED_DATA" ] || {{ echo "ERROR=Data_hash:$p" >> "$FAIL"; printf 'blocked\n' > "$STATUS"; exit 2; }}
done
for p in "$BASE/data/unique-chip-id" "$STAGE/data/unique-chip-id"; do
    [ ! -L "$p" ] && [ "$(sha256sum "$p" | cut -d ' ' -f1)" = "$EXPECTED_CHIP" ] || {{ echo "ERROR=chip_hash:$p" >> "$FAIL"; printf 'blocked\n' > "$STATUS"; exit 2; }}
done
[ "$(stat -c '%d:%i' "$BASE/data/data.img")" != "$(stat -c '%d:%i' "$STAGE/data/data.img")" ] || exit 2
[ "$(df -Pk "$STAGE" | awk 'END {{print $4}}')" -ge {MIN_FREE_KIB} ] || exit 2
[ -f "$BASE/image/kernel.kc.gpuaddon" ] && [ ! -L "$BASE/image/kernel.kc.gpuaddon" ] || {{ echo 'ERROR=missing_gpuaddon' >> "$FAIL"; printf 'blocked\n' > "$STATUS"; exit 2; }}
# The host supports trustcache sidecar OR manifest-backed trust modules (imageset.c).
# An image without kernel.kc.trustcache is valid when the signed owner module is present.
if [ -f "$BASE/image/kernel.kc.trustcache" ] && [ ! -L "$BASE/image/kernel.kc.trustcache" ]; then
    echo 'TRUST_SOURCE=kernel_sidecar' >> "$FAIL"
elif [ -f "$BASE/image/trust/static.trustcache" ] && [ ! -L "$BASE/image/trust/static.trustcache" ] && \
     [ -f "$BASE/image/overlay/userland/owner-trust.json" ] && [ ! -L "$BASE/image/overlay/userland/owner-trust.json" ]; then
    echo 'TRUST_SOURCE=imageset_static_plus_owner' >> "$FAIL"
else
    echo 'ERROR=missing_trustcache_source_or_owner_module' >> "$FAIL"
    printf 'blocked\n' > "$STATUS"
    exit 2
fi
mkdir -m 700 "$STAGE/{log_dir}/session" 2>/dev/null || exit 2
# Mark the candidate as consumed before its first writable guest open.
( set -C; echo "$(date -u)" > "$STAGE/gpu-bench/attempted" ) || exit 2
printf 'running\n' > "$STATUS"
printf 'MAP_COUNT_BEFORE=%s\n' "$(cat /proc/sys/vm/max_map_count)" >> "$FAIL"
echo 'GPU_MODE=auto' >> "$FAIL"
echo 'GPU_ADDON=existing_signed_and_trusted' >> "$FAIL"
# Keep Android's GUI and input devices untouched; use only the isolated APFS Data pair.
# The device-side timeout remains active even if USB/SSH disconnects.
ONEIOS_GPU_TRACE=1 timeout -s TERM -k 15 {seconds} "$STAGE/bin/{binary}" \\
    --mode bench \\
    --image "$BASE/image" \\
    --data "$STAGE/data" \\
    --session "$STAGE/{log_dir}/session" \\
    --cpus 4 --ram {memory_mib}M \\
    --gpu auto --display none --no-input \\
    --width 1080 --height 2340 --hz 60 \\
    --set bridges=0 \\
    > "$LOG" 2>&1
rc=$?
printf 'GUEST_EXIT=%s\n' "$rc" >> "$FAIL"
printf 'MAP_COUNT_AFTER=%s\n' "$(cat /proc/sys/vm/max_map_count)" >> "$FAIL"
printf 'FRAMEWORK_AFTER=%s\n' "$(getprop init.svc.zygote)" >> "$FAIL"
if pidof system_server >/dev/null 2>&1; then echo 'SYSTEM_SERVER_AFTER=yes' >> "$FAIL"; else echo 'SYSTEM_SERVER_AFTER=no' >> "$FAIL"; fi
printf 'finished:%s\n' "$rc" > "$STATUS"
exit 0
'''


def summarize_log(log):
    stamps = {
        "bootargs_vgpu_3d": bool(re.search(r'boot-args "[^"\n]*\bvgpu-3d=1\b', log)),
        "gpu_drm_native": bool(re.search(r'virtio GPU with the DRM native context', log)),
        "legacy_vulkan_failure": bool(re.search(r'VkResultCode\(-3\)|vkEnumeratePhysicalDevices result=-3', log)),
        "quartzcore_abort": bool(re.search(r'ogl-context\.cpp:1309|found != slist->end|backboardd\[[0-9]+\] status 0x6', log)),
        "guest_first_frame": bool(re.search(r'guest ready: first frame', log)),
    }
    fences = [int(n) for n in re.findall(r'\bbackboardd fences ([0-9]+)\b', log)]
    stamps["backboardd_fences_max"] = max(fences, default=0)
    stamps["gpu_execution_observed"] = (stamps["bootargs_vgpu_3d"] and
                                         stamps["gpu_drm_native"] and
                                         stamps["backboardd_fences_max"] > 0)
    return stamps


def inspect_stage(stage, harness, adb, report):
    """Read-only inspection of an earlier attempt; do not change snapshot or replay."""
    stage_name(stage)
    command = f'''set -eu
STAGE='{stage}'


for rel in gpu-bench/state gpu-bench/run.log gpu-bench/device-run.log gpu-bench/xnuhost.log; do
    p="$STAGE/$rel"
    if [ -f "$p" ] && [ ! -L "$p" ]; then
        printf '===== %s =====\n' "$rel"
        tail -n 80 "$p"
    else
        printf '===== %s MISSING =====\n' "$rel"
    fi
done
if [ -e "$STAGE/gpu-bench/attempted" ]; then
    echo BENCH_ATTEMPTED=YES
else
    echo BENCH_ATTEMPTED=NO
fi
if [ -f /data/local/tmp/oneios-m3q-ios27-bench/image/kernel.kc.trustcache ]; then
    echo TRUST_SIDECAR=YES
else
    echo TRUST_SIDECAR=NO
fi
if [ -f /data/local/tmp/oneios-m3q-ios27-bench/image/trust/static.trustcache ]; then
    echo TRUST_IMAGESET_STATIC=YES
else
    echo TRUST_IMAGESET_STATIC=NO
fi
if [ -f /data/local/tmp/oneios-m3q-ios27-bench/image/overlay/userland/owner-trust.json ]; then
    echo TRUST_IMAGESET_OWNER=YES
else
    echo TRUST_IMAGESET_OWNER=NO
fi
if pidof xnuhost xnuhost-gui-bench xnuhost-tasks >/dev/null 2>&1; then
    echo GUEST_CURRENTLY_RUNNING=YES
else
    echo GUEST_CURRENTLY_RUNNING=NO
fi
'''
    result = harness.root(adb, command, seconds=40)
    report["inspection"] = result.stdout
    print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")


def stage_and_run(args, harness, adb, report):
    stage = stage_name(args.stage)
    local = ROOT / "runtime/xnuhost/build/android/xnuhost"
    if not local.is_file():
        raise RuntimeError("build xnuhost first: make -C runtime/xnuhost -j8 build/android/xnuhost")
    if b"vgpu-3d=1" not in local.read_bytes():
        raise RuntimeError("xnuhost lacks the vgpu-3d=1 marker; rebuild source-fixed runtime")
    local_sha = digest(local)
    report["runtime"] = {"path": str(local), "sha256": local_sha, "size": local.stat().st_size}
    baseline = harness.decode_kv(harness.root(adb, harness.DEVICE_AUDIT).stdout)
    checks, failures = harness.validate_preflight(baseline)
    report["preflight"] = {"checks": checks, "failures": failures}
    if failures:
        raise RuntimeError("preflight blocked: " + ", ".join(failures))
    if args.action == "plan":
        print("PREFLIGHT=PASS\nGUEST_RUN_READY=BLOCKED (plan only)\nIMAGE_ADDON=EXISTING_TRUSTED")
        return
    nonce = secrets.token_hex(8)
    retry = args.action == "retry-preboot"
    log_dir = "gpu-bench/retry-preboot" if retry else "gpu-bench"
    runner_name = "run-gpu-retry.sh" if retry else "run-gpu.sh"
    incoming, setup = safe_shell(stage, local_sha, nonce, retry_preboot=retry)
    report["stage"] = stage
    report["duration_seconds"] = args.duration
    report["guest_ram_mib"] = args.ram_mib
    report["addon"] = "unchanged existing signed addon; no instrumented Vulkan API trace"
    try:
        harness.run([*adb, "push", str(local), incoming], seconds=90)
        prepared = harness.root(adb, setup, seconds=100)
        if "PREPARED=PASS" not in prepared.stdout:
            raise RuntimeError("device-side artifact staging did not pass")
        text = device_run_script(stage, args.duration, args.ram_mib, retry_preboot=retry)
        # The private stage is root-owned, mode 0700. Only our pinned snapshot is changed.
        install = "cat > '" + stage + "/bin/" + runner_name + "' <<'ONEIOS_RUN_EOF'\n" + text + "\nONEIOS_RUN_EOF\nchmod 700 '" + stage + "/bin/" + runner_name + "'\n"
        harness.root(adb, install, seconds=30)
        kick = ("set -eu\nnohup sh '" + stage + "/bin/" + runner_name + "' > '" +
                stage + "/" + log_dir + "/device-run.log' 2>&1 < /dev/null &\necho STARTED_PID=$!\n")
        launched = harness.root(adb, kick, seconds=20)
        report["launch"] = launched.stdout[-2000:]
        if "STARTED_PID=" not in launched.stdout:
            raise RuntimeError("detached runner launch not acknowledged")
        print("DEVICE_BENCH_STARTED=YES\nDURATION_LIMIT=" + str(args.duration) + "s")
        deadline = time.monotonic() + args.duration + 220
        state = "unknown"
        while time.monotonic() < deadline:
            r = harness.root(adb, "cat '" + stage + "/" + log_dir + "/state' 2>/dev/null || echo pending", seconds=18)
            state = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "pending"
            if state.startswith("finished:") or state.startswith("blocked"):
                break
            time.sleep(6)
        report["remote_state"] = state
        print("DEVICE_BENCH_STATE=" + state)
        if not (state.startswith("finished:") or state.startswith("blocked")):
            raise RuntimeError("remote deadline not confirmed; device-side timeout should still enforce bounded lifetime")
        host_log = harness.root(adb, "tail -n 7000 '" + stage + "/" + log_dir + "/xnuhost.log' 2>/dev/null || :", seconds=65).stdout
        device_log = harness.root(adb, "cat '" + stage + "/" + log_dir + "/run.log' 2>/dev/null || :", seconds=20).stdout
        logpath = Path(args.output).with_suffix(".xnuhost.log") if args.output else ROOT / "out/sm8850/gpu-acceptance" / (args.tag + "-ios-gpu-bench.log")
        logpath.parent.mkdir(parents=True, exist_ok=True)
        logpath.write_text(host_log)
        report["local_log"] = str(logpath)
        report["device_log"] = device_log
        report["device_error"] = re.findall(r"^ERROR=(.*)$", device_log, re.MULTILINE)
        print("DEVICE_RUN_LOG_BEGIN")
        print(device_log.strip() or "(empty; check device-run.log)")
        print("DEVICE_RUN_LOG_END")
        report["markers"] = summarize_log(host_log)
        report["IOS_VULKAN"] = "UNVERIFIED"  # Old addon has no vkCreateDevice instrumentation.
        print("GPU_BOOTARGS_VGPU3D=" + str(report["markers"]["bootargs_vgpu_3d"]))
        print("GPU_DRM_NATIVE=" + str(report["markers"]["gpu_drm_native"]))
        print("GPU_FENCES_MAX=" + str(report["markers"]["backboardd_fences_max"]))
        print("VK_ERROR_MINUS3=" + str(report["markers"]["legacy_vulkan_failure"]))
        print("QUARTZCORE_ABORT=" + str(report["markers"]["quartzcore_abort"]))
        print("IOS_VULKAN=UNVERIFIED (old signed addon; verify GPU rendering and errors)")
        if state.startswith("blocked"):
            raise RuntimeError("device-side guest bench blocked; see run.log and report")
    finally:
        try:
            harness.root(adb, "rm -f '" + incoming + "'", seconds=15)
        except Exception as error:
            report["upload_cleanup_warning"] = str(error)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("plan", "run", "inspect", "retry-preboot"))
    p.add_argument("--stage", required=True)
    p.add_argument("--duration", type=int, default=240)
    p.add_argument("--ram-mib", type=int, default=4096)
    p.add_argument("--adb", default=shutil.which("adb") or str(Path.home() / "Android/Sdk/platform-tools/adb"))
    p.add_argument("--serial")
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    stage_name(args.stage)
    if args.duration not in range(30, 301) or args.ram_mib not in range(2048, 5121, 256):
        p.error("duration must be 30..300 seconds and RAM 2048..5120 MiB in 256 MiB steps")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.tag = stamp
    output = args.output or ROOT / "out/sm8850/gpu-acceptance" / (stamp + "-ios-gpu-bench.json")
    report = {"action": args.action, "stage": args.stage, "IOS_VULKAN": "UNVERIFIED",
              "FRAMEWORK_TAKEOVER": "BLOCKED", "scope": "one-shot no-takeover bench, isolated Data"}
    rc = 0
    try:
        harness = load_harness()
        adb = harness.select_usb(args.adb, args.serial)
        report["serial"] = adb[-1]
        if args.action == "inspect":
            inspect_stage(args.stage, harness, adb, report)
        else:
            stage_and_run(args, harness, adb, report)
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as e:
        rc = 2
        report["error"] = str(e)
        print("BLOCKED: " + str(e), file=sys.stderr)
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("REPORT=" + str(output))
    return rc


if __name__ == "__main__":
    sys.exit(main())
