#!/usr/bin/env python3
"""Run the explicit SM-S948B Framework takeover profile through USB ADB."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid


REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
STAGE = "/data/adb/oneios-m3q-framework"
BENCH = "/data/local/tmp/oneios-m3q-ios27-bench"
ASSETS = REPO / "app/switcher/assets"
TARGET = "SM-S948B:m3q:SM8850"
ACK = "I_ACCEPT_SM8850_FRAMEWORK_TAKEOVER"
ADB_DEFAULT = Path.home() / "Android/Sdk/platform-tools/adb"
# The actual 3D xnuhost and display helpers come from the locally built,
# SHA-256-attested OneiOS binaries, NOT old runtime/bench files on the phone.
# Manifest the COMPLETE existing iOS image tree, including its trust modules.
REQUIRED = {
    "image/manifest.json", "image/kernel.kc", "image/kernel.kc.gpuaddon",
    "image/os.img", "image/systemos.img", "image/app.img",
}
STATUS = f"""stage={STAGE}
echo "boot=$(cat /proc/sys/kernel/random/boot_id)"
echo "boot_completed=$(getprop sys.boot_completed)"
echo "boot_reason=$(getprop ro.boot.bootreason)"
for name in boot state framework.mode framework.return framework.takeover-confirmed framework.launch framework.duration framework.deadline framework.result watchdog.phase thermal.guard.required thermal.cap.required thermal.guard.heartbeat thermal.cap.heartbeat thermal.guard.fault thermal.cap.fault; do
    if [ -f "$stage/control/$name" ]; then printf 'control/%s=' "$name"; cat "$stage/control/$name"; fi
done
if [ -f "$stage/return.outcome" ]; then printf 'outcome='; cat "$stage/return.outcome"; fi
if [ -f "$stage/session/return.request" ]; then
    printf 'return_request='
    head -c 160 "$stage/session/return.request" | tr '[:cntrl:]' ' '
    echo
fi
if [ -f "$stage/image.ready" ]; then echo image_ready=1; else echo image_ready=0; fi
if [ -f "$stage/session/ready" ]; then echo guest_ready=1; else echo guest_ready=0; fi
if grep -qm1 -F 'first frame posted' "$stage/control/display.log" 2>/dev/null; then
    echo display_first_frame=1
else
    echo display_first_frame=0
fi
if grep -qm1 -F 'ONEIOS_TAKEOVER_CPU=8' "$stage/session/xnuhost.log" 2>/dev/null; then
    echo guest_host_cpus=8_verified_mask
fi
for service in zygote zygote_next adbd surfaceflinger vendor.qti.hardware.display.composer; do
    printf '%s=%s pid=%s\n' "$service" "$(getprop init.svc.$service)" "$(getprop init.svc_debug_pid.$service)"
done
echo "system_server=$(pidof system_server)"
echo "SELinux=$(getenforce)"
echo "vm.max_map_count=$(cat /proc/sys/vm/max_map_count)"
if [ -f "$stage/smoke.accepted" ] && [ "$(cat "$stage/smoke.accepted")" = "$(cat /proc/sys/kernel/random/boot_id)" ]; then
    echo "smoke_current_boot=1"
else
    echo "smoke_current_boot=0"
fi
for group in /sys/fs/cgroup/apps/uid_*; do
    [ -d "$group" ] || continue
    if [ ! -r "$group/cgroup.events" ] || [ ! -w "$group/cgroup.kill" ]; then
        echo "framework_app_cgroup_draining=blocked"
        break
    fi
done
grep -E '^(MemAvailable|SwapFree):' /proc/meminfo
"""


class Phone:
    def __init__(self, adb, serial):
        self.adb = str(adb)
        listing = subprocess.check_output([self.adb, "devices", "-l"], text=True)
        usb = [line.split()[0] for line in listing.splitlines()
               if re.search(r"\sdevice\s+.*\busb:", line)]
        if not usb:
            raise RuntimeError("No authorized USB ADB device is connected")
        if serial is None and len(usb) == 1:
            serial = usb[0]
        if serial not in usb:
            raise RuntimeError("Specify exactly one authorized USB device with --serial")
        self.command = [self.adb, "-s", serial]
        target = self.call(["shell", "-T", "echo $(getprop ro.product.model):$(getprop ro.product.device):$(getprop ro.soc.model)"],
                           stdout=subprocess.PIPE, check=True).stdout.decode().strip()
        if target != TARGET:
            raise RuntimeError(f"Unexpected device {target!r}. Expected {TARGET}.")

    def call(self, args, **options):
        return subprocess.run(self.command + args, **options)

    def root(self, script, *, binary=False, **options):
        args = ["exec-out"] if binary else ["shell", "-T"]
        return self.call(args + ["su -c " + shlex.quote(script)], **options)


def manifest_bytes(path):
    entries = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})\s+(image/[A-Za-z0-9_][A-Za-z0-9._/+-]*)", line)
        if not match:
            raise ValueError(f"Malformed manifest line {line!r}")
        digest, name = match.groups()
        if any(part in {"", ".", ".."} for part in name.split("/")) or name in entries:
            raise ValueError(f"Unsafe or repeated benchmark path {name}")
        if ".." in name:
            raise ValueError(f"Incompatible staged image path {name}")
        entries[name] = digest
    if REQUIRED - entries.keys():
        raise ValueError(f"Manifest omits {', '.join(sorted(REQUIRED - entries.keys()))}")
    if not (
        "image/kernel.kc.trustcache" in entries or
        {"image/trust/static.trustcache",
         "image/overlay/userland/owner-trust.json"} <= entries.keys()
    ):
        raise ValueError("Image lacks a verified kernel trustcache sidecar or static+owner trust module")
    if any(parent.as_posix() in entries for name in entries for parent in Path(name).parents):
        raise ValueError("A benchmark path is both a file and a directory")
    return "".join(f"{digest}  {name}\n" for name, digest in sorted(entries.items())).encode()


def build_phone_tool(source, destination):
    ndk = Path(os.environ.get("ANDROID_NDK_ROOT", Path.home() / "Android/Sdk/ndk/28.2.13676358"))
    clang = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang"
    subprocess.run([clang, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", source, "-o", destination], check=True)


def upload(phone, operation, manifest=None):
    files = {name: ASSETS / name for name in (
        "oneios_switch.sh", "oneios_return.sh",
        "oneios_sm8850_thermal_cap.sh",
        "oneios_sm8850_thermal_takeover_guard.sh",
    )}
    files["stage.sh"] = HERE / "framework-stage.sh"
    with tempfile.TemporaryDirectory(prefix="oneios-framework-") as folder:
        if operation not in {"install", "upgrade"}:
            clone = Path(folder) / "image-copy"
            build_phone_tool(HERE / "framework-image-copy.c", clone)
            files["image-copy"] = clone
        if operation != "probe":
            supervisor = Path(folder) / "oneios-watchdog"
            build_phone_tool(ASSETS.parent / "native/oneios_watchdog.c", supervisor)
            files["oneios-watchdog"] = supervisor
        if operation in {"prepare", "upgrade-runtime"}:
            # Use the SAME locally built, GPU-3D/touch-capable artifacts as
            # the successful no-takeover visual runner. No old 2D runtime
            # is accepted in the full Framework mode.
            gpu_files = {
                "xnuhost": REPO / "runtime/xnuhost/build/android/xnuhost",
                "oneios-display": REPO / "runtime/display/build/android/oneios-display",
                "oneios-display.dex": REPO / "runtime/display/build/android/oneios-display.dex",
                "liboneios-display.so": REPO / "runtime/display/build/android/liboneios-display.so",
            }
            native_hashes = []
            for name, source in gpu_files.items():
                if not source.is_file() or source.is_symlink() or source.stat().st_size < 256:
                    raise ValueError(f"Build the current 3D guest/display locally first: {source}")
                if name == "xnuhost":
                    data = source.read_bytes()
                    if b"vgpu-3d=1" not in data or b"touch-exclusive=1 requires" not in data:
                        raise ValueError("xnuhost lacks validated GPU-3D/touch-exclusion markers")
                    # Full-bridges sessions must never stage an old bench-only
                    # xnuhost. Refuse before transmitting any package to ADB.
                    if (operation == "upgrade-runtime" and
                            subprocess.check_output(
                                ["git", "-C", str(REPO), "branch", "--show-current"],
                                text=True).strip() in {"feat/oneios-sm8850-m3q", "feat/sm8850-full-bridges-takeover"} and
                            b"SM8850_FULL_BRIDGES=ACTIVE" not in data):
                        raise ValueError("xnuhost lacks SM8850 full-bridges marker; refusing stage")
                files["native/" + name] = source
                native_hashes.append((hashlib.sha256(source.read_bytes()).hexdigest(), name))
            files["native.sha256"] = Path(folder) / "native.sha256"
            files["native.sha256"].write_text(
                "".join(f"{sha}  {name}\n" for sha, name in native_hashes)
            )
        with tempfile.TemporaryFile() as packet:
            with tarfile.open(fileobj=packet, mode="w") as tar:
                for name, path in files.items():
                    tar.add(path, arcname=name, recursive=False)
                if manifest is not None:
                    entry = tarfile.TarInfo("bench.sha256")
                    entry.size = len(manifest)
                    entry.mode = 0o600
                    tar.addfile(entry, io.BytesIO(manifest))
            packet.seek(0)
            return phone.root(f"""set -eu
umask 077
incoming=$(mktemp -d /data/adb/.oneios-m3q-upload.XXXXXX)
trap 'rm -rf "$incoming"' EXIT
tar -xf - -C "$incoming"
/system/bin/sh "$incoming/stage.sh" "$incoming" {operation}
""", stdin=packet, timeout=1200).returncode


def post_reboot_without_root(phone):
    """Passively read Android boot metadata when DirtyFrag su disappears.

    No su, root helper, reboot, mount, or device state changes.
    """
    script = """printf 'boot='; cat /proc/sys/kernel/random/boot_id
printf 'boot_completed='; getprop sys.boot_completed
printf 'boot_reason='; getprop ro.boot.bootreason
printf 'system_boot_reason='; getprop sys.boot.reason
printf 'last_boot_reason='; getprop sys.boot.reason.last
printf 'zygote='; getprop init.svc.zygote
printf 'system_server_pid='; pidof system_server || true
"""
    result = phone.call(
        ["shell", "-T", script], stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=8, check=True,
    )
    text = result.stdout.decode(errors="replace")
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    return values, text


def full_run_rootless_receipt(passive, *, guest_ready, display_first_frame, cpu_mask):
    """Describe *observed* facts without claiming root-only return proof.

    The device may have booted Android after OneOS's mandatory reboot,
    while ephemeral DirtyFrag root is gone. Guest-ready and display markers
    were observed BEFORE reboot; they must not be erased by status failure.
    An Android boot reason alone never certifies the exact deadline caller,
    an unassisted recovery path, or independent watchdog handback.
    """
    reason = passive.get("boot_reason", "UNKNOWN")
    system_server = passive.get("system_server_pid", "")
    return [
        "FULL_TAKEOVER_POST_REBOOT=ROOT_STATUS_UNAVAILABLE",
        "ANDROID_NEW_BOOT=" + (
            "BOOT_COMPLETED_OBSERVED_VIA_UNPRIVILEGED_ADB"
            if passive.get("boot_completed") == "1" else "NOT_VERIFIED"
        ),
        "BOOT_REASON=" + reason,
        "IOS_GUEST_READY_PRE_REBOOT=" + ("OBSERVED" if guest_ready else "NOT_VERIFIED"),
        "IOS_DISPLAY_FIRST_FRAME_PRE_REBOOT=" + ("OBSERVED" if display_first_frame else "NOT_VERIFIED"),
        "IOS_HOST_CPU_MASK_PRE_REBOOT=" + ("0-7_OBSERVED" if cpu_mask else "NOT_VERIFIED"),
        "IOS_GUEST_START_PRE_REBOOT=" + (
            "OBSERVED" if guest_ready and display_first_frame else "NOT_VERIFIED"
        ),
        "ANDROID_SYSTEM_SERVER_AFTER_REBOOT=" + (
            "PID_OBSERVED" if system_server.isdecimal() else "NOT_VERIFIED"
        ),
        "FULL_TAKEOVER_DEADLINE_RETURN=NOT_VERIFIED_NO_ROOT_OUTCOME",
        "UNASSISTED_RETURN_TO_ONEUI=NOT_VERIFIED",
        "WATCHDOG_QUALIFICATION=UNVERIFIED_REBOOT_ONLY",
    ]


def status(phone, token=None):
    script = STATUS
    if token:
        script += f"""if [ -f "$stage/launches/{token}/exit" ]; then
    printf 'launch_exit='; cat "$stage/launches/{token}/exit"
fi
"""
    result = phone.root(script, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8, check=True)
    return result.stdout.decode()


def audit(phone, destination=None, *, reboot_only=False):
    audit_mode = "--framework-audit-reboot" if reboot_only else "--framework-audit"
    result = phone.root("/system/bin/sh -s -- " + audit_mode,
                        input=(ASSETS / "oneios_switch.sh").read_bytes(), stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=20)
    if destination:
        destination.write_bytes(result.stdout)
    print(result.stdout.decode(), end="", flush=True)
    return result.returncode


def collect(phone, output):
    with (output / "device-logs.tar").open("wb") as archive:
        result = phone.root(f"""cd {STAGE} || exit 1
set --
for name in launches return.log return.outcome control session logs thermal-guard.log thermal-cap.log thermal.guard.manifest; do
    if [ -e "$name" ]; then set -- "$@" "$name"; fi
done
[ $# -gt 0 ] && tar --exclude=display.sock -cf - "$@"
""", binary=True, stdout=archive, timeout=90)
    if result.returncode:
        print("Device log archive is incomplete. Device files remain available.", file=sys.stderr)
    else:
        # Post-process the ARCHIVE ONLY; never let analytical failure change
        # reboot/return handling. This is not a guest tracing hot-path.
        report_file = output / "frame-stall-report.json"
        try:
            p = subprocess.run(
                [sys.executable, str(HERE / "sm8850-frame-stall-report.py"),
                 "--archive", str(output / "device-logs.tar"),
                 "--output", str(report_file)],
                capture_output=True, text=True, timeout=25,
            )
            if p.returncode == 0:
                print("FRAME_STALL_REPORT=" + str(report_file), flush=True)
            elif p.returncode == 3 and "FRAME_STALL_REPORT=SKIPPED_MISSING_GUEST_TRACE" in p.stderr:
                # Thermal/recovery-only captures may have no guest traces;
                # this does not invalidate the device archive or return logs.
                print(p.stderr.strip(), flush=True)
            else:
                error_file = output / "frame-stall-error.txt"
                error_file.write_text(
                    f"exit={p.returncode}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}",
                    encoding="utf-8",
                )
                reason = p.stderr.strip().splitlines()[-1] if p.stderr.strip() else f"exit={p.returncode}"
                print(f"FRAME_STALL_REPORT=UNAVAILABLE reason={reason[:180]} "
                      f"full_error={error_file}", flush=True)
        except (OSError, subprocess.TimeoutExpired) as error:
            error_file = output / "frame-stall-error.txt"
            error_file.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
            print(f"FRAME_STALL_REPORT=UNAVAILABLE {type(error).__name__} "
                  f"full_error={error_file}", flush=True)
    with (output / "restored-device.txt").open("wb") as details:
        diagnostic = phone.root(STATUS + """
echo '=== Input services ==='
dumpsys --pid inputflinger
dumpsys --pid input
timeout 10 dumpsys input
echo '=== User 0 ==='
timeout 5 am get-started-user-state 0
echo '=== Watchdog and Android crash buffers ==='
logcat -d -b crash -v threadtime
echo '=== Current kernel log ==='
timeout 10 dmesg
echo '=== Persistent kernel crash files ==='
for file in /sys/fs/pstore/console-ramoops* /sys/fs/pstore/dmesg-ramoops*; do
    [ -f "$file" ] || continue
    echo "$file"
    timeout 4 cat "$file"
done
""", stdout=details, stderr=subprocess.STDOUT, timeout=30)
    return result.returncode == 0 and diagnostic.returncode == 0


def interpret_readiness(audit_rc, audit_log, details):
    """Strictly diagnostic: audit never authorizes a live Framework stop."""
    values = dict(line.split("=", 1) for line in details.splitlines() if "=" in line)
    blockers = []
    if audit_rc != 0:
        reasons = [line for line in audit_log.splitlines()
                   if line.startswith(("BLOCKED:", "PREFLIGHT REFUSED:"))]
        blockers.extend(reasons or [f"Framework audit failed, rc={audit_rc}; see audit.txt"])
    if not values.get("zygote", "").startswith("running pid=") or not values.get("system_server", "").isdecimal():
        blockers.append("Android Framework is not healthy on the inspected boot")
    if values.get("SELinux") != "Enforcing":
        blockers.append("SELinux is not Enforcing")
    if values.get("framework_app_cgroup_draining") == "blocked":
        blockers.append("At least one Android app cgroup cannot be drained by the current script")
    if values.get("image_ready") != "1":
        blockers.append("Independent takeover image/Data stage not finalized")
    if values.get("smoke_current_boot") != "1":
        blockers.append("No verified recovery smoke accepted on the current boot")
    # A passing passive audit cannot verify physical handback or justify
    # mutating system_server. The operator must independently accept watchdog,
    # recovery, and return gates for this exact firmware and boot.
    return {
        "phase": "SM8850_TAKEOVER_GATE0",
        "scope": "READ_ONLY_NO_FRAMEWORK_STOP_NO_WATCHDOG_OPEN",
        "audit_exit_code": audit_rc,
        "audit_pass": audit_rc == 0,
        "status": values,
        "blockers": blockers,
        "live_takeover_authorized": False,
        "next_gate": "Independent physical watchdog/return qualification, stage, and smoke acceptance",
    }


def readiness(phone, output):
    """Passive root metadata/audit only. Never calls upload, launch or return."""
    result = phone.root("/system/bin/sh -s -- --framework-audit",
                        input=(ASSETS / "oneios_switch.sh").read_bytes(),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25)
    audit_log = result.stdout.decode(errors="replace")
    (output / "audit.txt").write_text(audit_log)
    try:
        details = status(phone)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        details = "status_error=" + str(error) + "\n"
    (output / "status.txt").write_text(details)
    report = interpret_readiness(result.returncode, audit_log, details)
    (output / "readiness.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("READINESS_MODE=READ_ONLY")
    print("FRAMEWORK_AUDIT=" + ("PASS" if report["audit_pass"] else "BLOCKED"))
    print("LIVE_TAKEOVER_AUTHORIZED=NO")
    for why in report["blockers"]:
        print("BLOCKER=" + why)
    if not report["blockers"]:
        print("NEXT_GATE=Independent watchdog and physical return review still required")
    print("READINESS_REPORT=" + str(output / "readiness.json"))
    print("READINESS_AUDIT=" + str(output / "audit.txt"))
    return 0  # Captured a diagnostic, not a permission or live success.


def restored_on_same_boot(baseline, after, mode):
    before = dict(line.split("=", 1) for line in baseline.splitlines() if "=" in line)
    now = dict(line.split("=", 1) for line in after.splitlines() if "=" in line)
    protected = ("adbd", "surfaceflinger", "vendor.qti.hardware.display.composer")
    return (
        all(now.get(key) and now[key] == before.get(key) for key in ("boot", "vm.max_map_count", *protected))
        and all(now[key].startswith("running pid=") for key in protected)
        and now.get("zygote", "").startswith("running pid=")
        and now.get("zygote_next", "").startswith("running pid=")
        and now.get("system_server", "").isdecimal() and now["system_server"] != before.get("system_server")
        and now.get("SELinux") == "Enforcing"
        and now.get("outcome", "").startswith("inplace ")
        and now.get("control/framework.result") == f"{mode} complete"
    )


def reboot_stage_check(phone, output):
    """Install recovery scripts and verify reboot-smoke preflight; never stop Framework."""
    if audit(phone, output / "preflight.txt", reboot_only=True):
        return 2
    if upload(phone, "upgrade"):
        return 2
    check = phone.root(
        f"/system/bin/sh {STAGE}/oneios_switch.sh --framework-check reboot-smoke",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
    )
    (output / "stage-check.txt").write_bytes(check.stdout)
    print(check.stdout.decode(errors="replace"), end="", flush=True)
    print("REBOOT_STAGE_CHECK=" + ("PASS_NO_FRAMEWORK_STOP" if check.returncode == 0
                                  else "BLOCKED"))
    return 0 if check.returncode == 0 else 2

def reboot_smoke_ready(state, baseline_boot, token):
    """Only tell the operator to press the chord after the verified stop."""
    values = dict(line.split("=", 1) for line in state.splitlines() if "=" in line)
    return (
        values.get("boot") == baseline_boot
        and values.get("control/framework.launch") == token
        and values.get("control/framework.mode") == "smoke"
        and values.get("control/framework.return") == "reboot"
        and values.get("control/state") == "running"
        and bool(values.get("control/framework.takeover-confirmed"))
        and values.get("zygote", "").startswith("stopped")
        and not values.get("system_server")
        and "return_request=" not in state
    )


def reboot_smoke_verified(baseline, after):
    """Success requires recorded Framework stop, key-triggered reboot and healthy One UI."""
    before = dict(line.split("=", 1) for line in baseline.splitlines() if "=" in line)
    now = dict(line.split("=", 1) for line in after.splitlines() if "=" in line)
    return (
        bool(before.get("boot")) and bool(now.get("boot")) and now["boot"] != before["boot"]
        and now.get("boot_completed") == "1"
        and now.get("control/framework.mode") == "smoke"
        and now.get("control/framework.return") == "reboot"
        and bool(now.get("control/framework.takeover-confirmed"))
        and now.get("outcome", "").startswith("reboot-key ")
        and now.get("zygote", "").startswith("running pid=")
        and now.get("zygote_next", "").startswith("running pid=")
        and now.get("system_server", "").isdecimal()
        and now.get("SELinux") == "Enforcing"
    )


def reboot_smoke_deadline_verified(baseline, after, token):
    """Verify deadline request and a later healthy boot, not an unassisted boot path."""
    before = dict(line.split("=", 1) for line in baseline.splitlines() if "=" in line)
    now = dict(line.split("=", 1) for line in after.splitlines() if "=" in line)
    return (
        bool(before.get("boot")) and bool(now.get("boot"))
        and now["boot"] != before["boot"]
        and now.get("boot_completed") == "1"
        and now.get("boot_reason") == "reboot,oneios-sm8850-reboot-return"
        and now.get("control/framework.launch") == token
        and now.get("control/framework.mode") == "smoke"
        and now.get("control/framework.return") == "reboot"
        and bool(now.get("control/framework.takeover-confirmed"))
        and now.get("outcome", "").startswith("reboot-deadline-or-manual ")
        and now.get("return_request", "").startswith("framework deadline reached")
        and now.get("zygote", "").startswith("running pid=")
        and now.get("zygote_next", "").startswith("running pid=")
        and now.get("system_server", "").isdecimal()
        and now.get("SELinux") == "Enforcing"
    )


def full_takeover_deadline_result(baseline, after, token):
    """Physical guest session ended by deadline; NOT unassisted normal-boot proof."""
    before = dict(line.split("=", 1) for line in baseline.splitlines() if "=" in line)
    now = dict(line.split("=", 1) for line in after.splitlines() if "=" in line)
    return (
        bool(before.get("boot")) and bool(now.get("boot"))
        and now["boot"] != before["boot"]
        and now.get("boot_completed") == "1"
        and now.get("boot_reason") == "reboot,oneios-sm8850-reboot-return"
        and now.get("control/framework.launch") == token
        and now.get("control/framework.mode") == "run"
        and now.get("control/framework.return") == "reboot"
        and bool(now.get("control/framework.takeover-confirmed"))
        and now.get("outcome", "").startswith("reboot-deadline-or-manual ")
        and "who=framework-deadline" in now.get("outcome", "")
        and now.get("return_request", "").startswith("framework deadline reached")
        and now.get("zygote", "").startswith("running pid=")
        and now.get("zygote_next", "").startswith("running pid=")
        and now.get("system_server", "").isdecimal()
        and now.get("SELinux") == "Enforcing"
    )


def launch(phone, mode, output, *, reboot_only=False, duration=600,
           passive_soft_thermal=False):
    # SM8850 full-run deliberately uses the same legacy OneOS V watchdog
    # feeder and mandatory reboot-return path as the observed smoke.
    # It is separately risk-acknowledged, NEVER an in-place handback.
    legacy_reboot = reboot_only or mode == "run"
    if passive_soft_thermal and (mode != "run" or duration != 180):
        raise ValueError("passive software thermal experiment requires exactly 180s run")
    # Prefix only the root-owned switch, including its admission check.
    # No persistent Android property or stale stage toggle is left behind.
    experimental_prefix = (
        "ONEIOS_SM8850_EXPERIMENT_NO_SOFT_THERMAL=I_ACCEPT_SOFT_GUARD_OFF_180S "
        if passive_soft_thermal else ""
    )
    if audit(phone, output / "preflight.txt", reboot_only=legacy_reboot):
        return 2
    if upload(phone, "upgrade" if legacy_reboot else "install"):
        return 2
    shell = f"/system/bin/sh {STAGE}/oneios_switch.sh"
    session_mode = "reboot-smoke" if reboot_only else mode
    check = phone.root(f"{experimental_prefix}{shell} --framework-check {session_mode}" +
                       (f" {duration}" if mode == "run" else ""), timeout=120)
    if check.returncode:
        return check.returncode
    baseline = status(phone)
    (output / "baseline.txt").write_text(baseline)
    boot = re.search(r"^boot=(.+)$", baseline, re.M).group(1)
    token = uuid.uuid4().hex
    risk_token = " I_ACCEPT_LEGACY_WATCHDOG_FULL_600S_RISK" if mode == "run" else ""
    duration_token = f" {duration}" if mode == "run" else ""
    if phone.root(f"""set -eu
umask 077
cd {STAGE}
mkdir -p launches
mkdir launches/{token}
/data/adb/ksu/bin/busybox setsid /system/bin/sh -c '
    {experimental_prefix}{shell} --framework-session {session_mode} {ACK} {token}{risk_token}{duration_token}
    rc=$?
    printf "%s\n" "$rc" > launches/{token}/exit
' </dev/null > launches/{token}/switch.log 2>&1 &
""", timeout=10).returncode:
        return 2
    print(f"Framework {session_mode} requested. Recovery runs on the device.", flush=True)
    if legacy_reboot:
        print("PHYSICAL_KEYS=DO_NOT_PRESS_VOLUME_UP_PLUS_DOWN", flush=True)
        print("USB + both Samsung volume keys can enter Download Mode during reboot.", flush=True)
        if mode == "run":
            print("FULL_TAKEOVER=REQUESTED", flush=True)
            print("GUEST_VCPUS=8; GPU=3d/required-no-fallback; TOUCH_EXCLUSIVE=YES; RAM=4GiB", flush=True)
            print("GPU_3D_STATUS=BACKEND_MUST_BE_CONFIRMED_IN_XNUHOST_LOG", flush=True)
            if passive_soft_thermal:
                print("SM8850_SOFT_THERMAL_GUARD=OFF_NO_PROCESS_NO_HEARTBEAT", flush=True)
                print("CPU_UNDERCLOCK=NONFATAL_BEST_EFFORT_FIXED_28_PERCENT_REQUEST", flush=True)
                print("WARNING=CAP_FAILURE_NO_SOFTWARE_REBOOT_AND_VENDOR_MINIMUM_MAY_OVERRIDE_CAP", flush=True)
            else:
                print("SM8850_SOFT_THERMAL_GUARD=DEFAULT_FAIL_CLOSED", flush=True)
            print("BRIDGES=1; CPU_PIN=1; CPU_AFFINITY_BENCH=0; GPU=3D_REQUIRED", flush=True)
            print("THERMAL_KERNEL_FIRMWARE_GUARDS=STILL_PRESENT_NOT_INDEPENDENTLY_VERIFIED", flush=True)
            print(f"DEADLINE_RETURN={duration}_SECONDS_AFTER_FRAMEWORK_STOP", flush=True)
            print("RECOVERY=MANDATORY_REBOOT_NOT_INPLACE; WATCHDOG_LEGACY_UNQUALIFIED=YES", flush=True)
        else:
            print("This smoke has a 20-second automatic reboot deadline AFTER Framework takeover.", flush=True)
        print("Do NOT press Volume Up + Down during this session.", flush=True)
    end = time.monotonic() + (max(duration, 60) + 400 if mode == "run" else 1000)
    reboot_seen = None
    confirmed_announced = False
    full_guest_seen = False
    full_display_seen = False
    full_cpu_seen = False
    with (output / "timeline.txt").open("w") as timeline:
        while time.monotonic() < end:
            try:
                state = status(phone, token)
                timeline.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n{state}\n")
                timeline.flush()
                current_boot = re.search(r"^boot=(.+)$", state, re.M).group(1)
                if mode == "run" and current_boot == boot and f"control/framework.launch={token}" in state:
                    kv = dict(line.split("=", 1) for line in state.splitlines() if "=" in line)
                    if kv.get("control/state") == "running" and kv.get("control/framework.takeover-confirmed"):
                        if not confirmed_announced:
                            print(f"FRAMEWORK_TAKEOVER=CONFIRMED; DEADLINE={duration}_SECONDS; DO_NOT_PRESS_VOLUME_KEYS", flush=True)
                            confirmed_announced = True
                        if kv.get("guest_ready") == "1" and not full_guest_seen:
                            full_guest_seen = True
                            print("IOS_GUEST_READY=OBSERVED", flush=True)
                        if kv.get("display_first_frame") == "1" and not full_display_seen:
                            full_display_seen = True
                            print("IOS_DISPLAY_FIRST_FRAME=OBSERVED", flush=True)
                        if kv.get("guest_host_cpus") == "8_verified_mask" and not full_cpu_seen:
                            full_cpu_seen = True
                            print("IOS_HOST_CPU_MASK=0-7", flush=True)
                if mode == "run" and current_boot != boot:
                    if full_takeover_deadline_result(baseline, state, token):
                        collect(phone, output)
                        print("FULL_TAKEOVER_DEADLINE_RETURN=REQUESTED_AND_ONEUI_OBSERVED", flush=True)
                        print("IOS_GUEST_READY=" + ("OBSERVED" if full_guest_seen else "NOT_VERIFIED"), flush=True)
                        print("IOS_DISPLAY_FIRST_FRAME=" + ("OBSERVED" if full_display_seen else "NOT_VERIFIED"), flush=True)
                        print("IOS_HOST_CPU_MASK=" + ("0-7" if full_cpu_seen else "NOT_VERIFIED"), flush=True)
                        print("UNASSISTED_RETURN_TO_ONEUI=NOT_VERIFIED", flush=True)
                        return 4
                    if reboot_seen is None:
                        reboot_seen = time.monotonic()
                    if time.monotonic() - reboot_seen > 120:
                        collect(phone, output)
                        print("FULL_TAKEOVER_REBOOT=INCOMPLETE_OR_UNEXPECTED", flush=True)
                        return 4
                    time.sleep(2)
                    continue
                if reboot_only and not confirmed_announced and reboot_smoke_ready(state, boot, token):
                    print("TAKEOVER_CONFIRMED=YES", flush=True)
                    print("PHYSICAL_KEYS=DO_NOT_PRESS_VOLUME_UP_PLUS_DOWN", flush=True)
                    print("AUTO_REBOOT=EXPECTED_AFTER_20_SECOND_FRAMEWORK_DEADLINE", flush=True)
                    print("This is Framework-only smoke, not iOS boot or physical-key PASS.", flush=True)
                    confirmed_announced = True
                if reboot_only and current_boot != boot:
                    # Do not fail early when the phone has rebooted but
                    # boot_completed/zygote_next/system_server are still starting.
                    if reboot_smoke_deadline_verified(baseline, state, token):
                        collect(phone, output)
                        print("REBOOT_SMOKE=DEADLINE_REQUEST_CONFIRMED_ONEUI_OBSERVED")
                        print("UNASSISTED_RETURN_TO_ONEUI=NOT_VERIFIED")
                        print("PHYSICAL_KEY_REBOOT=NOT_VERIFIED")
                        print("This evidence cannot exclude a Download Mode detour or manual force restart.")
                        return 4
                    if reboot_smoke_verified(baseline, state):
                        collect(phone, output)
                        print("REBOOT_SMOKE=KEY_RETURN_REQUEST_RECORDED_BOOT_MODE_UNVERIFIED")
                        print("PHYSICAL_KEY_REBOOT=NOT_VERIFIED")
                        return 4
                    if reboot_seen is None:
                        reboot_seen = time.monotonic()
                    if time.monotonic() - reboot_seen >= 120:
                        collect(phone, output)
                        print("REBOOT_SMOKE=INCOMPLETE_OR_AUTOMATIC_REBOOT")
                        return 4
                    time.sleep(2)
                    continue
                if current_boot != boot and "zygote=running" in state:
                    collect(phone, output)
                    print("Device rebooted during recovery. See the archived evidence.", file=sys.stderr)
                    return 4
                this_session = f"control/framework.launch={token}" in state
                if this_session and "control/state=returned" in state and "launch_exit=" in state:
                    collected = collect(phone, output)
                    if reboot_only:
                        # A successful key-triggered reboot cannot return on
                        # the same boot. Do not apply the in-place predicate
                        # and then report the misleading generic failure.
                        values = dict(line.split("=", 1) for line in state.splitlines() if "=" in line)
                        took_over = bool(values.get("control/framework.takeover-confirmed"))
                        print("REBOOT_SMOKE=" + ("SAME_BOOT_RETURNED_NO_KEY_REBOOT" if took_over
                                               else "ABORTED_BEFORE_FRAMEWORK_STOP"))
                        print("TAKEOVER_MARKER=" + str(took_over))
                        print("RETURN_OUTCOME=" + values.get("outcome", "UNAVAILABLE"))
                        print("See device-logs.tar / launches/*/switch.log for the earliest failure.")
                        return 4
                    restored = collected and restored_on_same_boot(baseline, state, mode)
                    print("Device reported an in-place return. Review the archived evidence." if restored
                          else "Recovery or phase verification failed. See the archived evidence.")
                    return 0 if restored else 4
                active = any(f"control/state={phase}" in state for phase in ("starting", "running", "returning"))
                if re.search(r"^launch_exit=[1-9]", state, re.M) and (not this_session or not active):
                    collect(phone, output)
                    if reboot_only:
                        print("REBOOT_SMOKE=SWITCH_EXITED_BEFORE_VERIFIED_KEY_REBOOT")
                        print("See device-logs.tar / launches/*/switch.log for the earliest failure.")
                    return 4
            except (subprocess.SubprocessError, OSError) as error:
                # A CalledProcessError contains the complete multi-line
                # 'su -c' script in its repr. Repeating that every 2 s
                # produced a 55 KiB "ADB unavailable" log with no new
                # diagnostic information after ephemeral root was lost.
                code = getattr(error, "returncode", None)
                failure = type(error).__name__
                if code is not None:
                    failure += f" exit={code}"
                timeline.write(f"Root/ADB status unavailable: {failure}\n")
                timeline.flush()
                if mode == "run":
                    # The device may have booted successfully but permanently
                    # lost its *ephemeral* DirtyFrag root. The normal status()
                    # uses su and would otherwise poll for 1000 seconds.
                    # Only conclude this when a new, boot-complete Android
                    # boot is visible to UNPRIVILEGED ADB.
                    try:
                        passive, passive_text = post_reboot_without_root(phone)
                    except (subprocess.SubprocessError, OSError):
                        pass  # USB disconnected or phone not boot-complete yet
                    else:
                        if passive.get("boot") not in {None, "", boot} and passive.get("boot_completed") == "1":
                            (output / "post-reboot-no-root.txt").write_text(passive_text)
                            timeline.write("POST_REBOOT_UNPRIVILEGED\n" + passive_text + "\n")
                            timeline.flush()
                            for line in full_run_rootless_receipt(
                                passive, guest_ready=full_guest_seen,
                                display_first_frame=full_display_seen,
                                cpu_mask=full_cpu_seen,
                            ):
                                print(line, flush=True)
                            print("Root may have disappeared because DirtyFrag is ephemeral.", flush=True)
                            print("Device booted; preserving stage evidence without another takeover.", flush=True)
                            return 4
            time.sleep(2)
    print("Device observation timed out. Recheck --status and retain the device logs.", file=sys.stderr)
    return 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("dry-run", "reboot-audit", "readiness", "recovery-smoke", "reboot-stage-check", "reboot-smoke", "run", "return", "status", "storage-probe", "prepare", "rearm-data", "upgrade-runtime", "collect"):
        modes.add_argument(f"--{mode}", dest="mode", action="store_const", const=mode)
    parser.add_argument("--confirm", action="store_true", help="Explicitly opt in to the requested device changes")
    parser.add_argument("--accept-legacy-watchdog-risk", action="store_true",
                        help="Separate risk consent for SM8850 legacy a:82 mandatory-reboot smoke OR 600-second full iOS takeover")
    parser.add_argument("--serial", help="ADB USB serial. Defaults to the sole authorized USB device.")
    parser.add_argument("--adb", type=Path, default=ADB_DEFAULT)
    parser.add_argument("--duration", type=int, help="Full run only: 60..600 seconds; default 600")
    parser.add_argument("--no-userspace-thermal-180", "--passive-soft-thermal-180",
                        dest="passive_soft_thermal_180", action="store_true",
                        help="exact 180s full-bridges: no on-device thermal guard, nonfatal best-effort 28pct CPU cap; kernel thermal unchanged")
    parser.add_argument("--gpu", choices=["3d"])
    parser.add_argument("--bench-manifest", type=Path)
    parser.add_argument("--output", type=Path, help="New local evidence directory")
    args = parser.parse_args()
    if args.mode in {"recovery-smoke", "reboot-stage-check", "reboot-smoke", "run", "storage-probe", "prepare", "rearm-data", "upgrade-runtime"} and not args.confirm:
        parser.error(f"--{args.mode} requires --confirm")
    if args.mode in {"reboot-smoke", "run"} and not args.accept_legacy_watchdog_risk:
        parser.error(f"--{args.mode} requires separate --accept-legacy-watchdog-risk consent")
    if args.mode == "run" and (args.gpu != "3d" or (args.duration is not None and
                                  not 60 <= args.duration <= 600)):
        parser.error("--run requires --gpu 3d and --duration between 60 and 600 seconds (default 600)")
    if args.mode != "run" and (args.duration is not None or args.gpu):
        parser.error("--duration and --gpu apply to --run")
    if args.passive_soft_thermal_180 and (args.mode != "run" or args.duration != 180):
        parser.error("--no-userspace-thermal-180 requires --run --duration 180")
    if (args.mode == "prepare") != bool(args.bench_manifest):
        parser.error("--prepare requires --bench-manifest with an independently verified benchmark SHA-256 list")
    manifest = manifest_bytes(args.bench_manifest) if args.bench_manifest else None
    phone = Phone(args.adb, args.serial)
    if args.mode == "dry-run":
        return audit(phone)
    if args.mode == "reboot-audit":
        return audit(phone, reboot_only=True)
    if args.mode == "status":
        print(status(phone), end="")
        return 0
    if args.mode == "return":
        return phone.root(f"if [ -f {STAGE}/oneios_switch.sh ]; then "
                          f"/system/bin/sh {STAGE}/oneios_switch.sh --framework-return; "
                          "else echo 'No experimental stage'; fi", timeout=650).returncode
    if args.mode in {"storage-probe", "prepare", "rearm-data", "upgrade-runtime"}:
        operation = "probe" if args.mode == "storage-probe" else args.mode
        return upload(phone, operation, manifest)

    output = args.output
    if output is None:
        root = REPO / "out/sm8850/takeover"
        root.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix=args.mode + "-", dir=root))
    else:
        output.mkdir(parents=True, mode=0o700)
    print(f"Local evidence: {output}", flush=True)
    if args.mode == "readiness":
        return readiness(phone, output)
    if args.mode == "collect":
        return 0 if collect(phone, output) else 4
    if args.mode == "reboot-stage-check":
        return reboot_stage_check(phone, output)
    if args.mode == "reboot-smoke":
        return launch(phone, "smoke", output, reboot_only=True)
    return launch(phone, "smoke" if args.mode == "recovery-smoke" else "run", output,
                  duration=args.duration if args.duration is not None else 600,
                  passive_soft_thermal=args.passive_soft_thermal_180)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"SM8850 takeover: {error}", file=sys.stderr)
        sys.exit(2)
