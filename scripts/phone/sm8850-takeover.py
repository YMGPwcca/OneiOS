#!/usr/bin/env python3
"""Run the explicit SM-S948B Framework takeover profile through USB ADB."""

import argparse
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
REQUIRED = {
    "bench/xnuhost-gui-bench", "image/manifest.json", "image/kernel.kc",
    "image/kernel.kc.hashes", "image/kernel.kc.gpuaddon", "image/kernel.kc.trustcache",
    "image/os.img", "image/systemos.img", "image/app.img", "image/data.seed",
    "image/os.img.hashes", "image/systemos.img.hashes", "image/app.img.hashes",
    "image/trust/static.trustcache", "image/trust/app.trustcache",
    "image/trust/system.trustcache", "image/trust/os.root_hash",
    "image/trust/system.root_hash", "image/trust/app.root_hash",
    "runtime/runtime.json", "runtime/bin/oneios-display", "runtime/bin/liboneios-display.so",
    "runtime/lib/oneios-display.dex",
}
STATUS = f"""stage={STAGE}
echo "boot=$(cat /proc/sys/kernel/random/boot_id)"
for name in boot state framework.mode framework.launch framework.deadline framework.result watchdog.phase; do
    if [ -f "$stage/control/$name" ]; then printf 'control/%s=' "$name"; cat "$stage/control/$name"; fi
done
if [ -f "$stage/return.outcome" ]; then printf 'outcome='; cat "$stage/return.outcome"; fi
if [ -f "$stage/image.ready" ]; then echo image_ready=1; else echo image_ready=0; fi
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
        match = re.fullmatch(r"([0-9a-f]{64})\s+((?:image|runtime|bench)/[A-Za-z0-9_][A-Za-z0-9._/+-]*)", line)
        if not match:
            raise ValueError(f"Malformed manifest line {line!r}")
        digest, name = match.groups()
        if any(part in {"", ".", ".."} for part in name.split("/")) or name in entries:
            raise ValueError(f"Unsafe or repeated benchmark path {name}")
        if name.startswith("bench/") and name != "bench/xnuhost-gui-bench":
            raise ValueError(f"Unexpected benchmark executable {name}")
        if ".." in name or name == "runtime/bin/xnuhost-gui-bench":
            raise ValueError(f"Incompatible staged path {name}")
        entries[name] = digest
    if REQUIRED - entries.keys():
        raise ValueError(f"Manifest omits {', '.join(sorted(REQUIRED - entries.keys()))}")
    if any(parent.as_posix() in entries for name in entries for parent in Path(name).parents):
        raise ValueError("A benchmark path is both a file and a directory")
    return "".join(f"{digest}  {name}\n" for name, digest in sorted(entries.items())).encode()


def build_phone_tool(source, destination):
    ndk = Path(os.environ.get("ANDROID_NDK_ROOT", Path.home() / "Android/Sdk/ndk/28.2.13676358"))
    clang = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang"
    subprocess.run([clang, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", source, "-o", destination], check=True)


def upload(phone, operation, manifest=None):
    files = {name: ASSETS / name for name in ("oneios_switch.sh", "oneios_return.sh")}
    files["stage.sh"] = HERE / "framework-stage.sh"
    with tempfile.TemporaryDirectory(prefix="oneios-framework-") as folder:
        if operation != "install":
            clone = Path(folder) / "image-copy"
            build_phone_tool(HERE / "framework-image-copy.c", clone)
            files["image-copy"] = clone
        if operation != "probe":
            supervisor = Path(folder) / "oneios-watchdog"
            build_phone_tool(ASSETS.parent / "native/oneios_watchdog.c", supervisor)
            files["oneios-watchdog"] = supervisor
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


def status(phone, token=None):
    script = STATUS
    if token:
        script += f"""if [ -f "$stage/launches/{token}/exit" ]; then
    printf 'launch_exit='; cat "$stage/launches/{token}/exit"
fi
"""
    result = phone.root(script, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8, check=True)
    return result.stdout.decode()


def audit(phone, destination=None):
    result = phone.root("/system/bin/sh -s -- --framework-audit",
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
for name in launches return.log return.outcome control session logs; do
    if [ -e "$name" ]; then set -- "$@" "$name"; fi
done
[ $# -gt 0 ] && tar --exclude=display.sock -cf - "$@"
""", binary=True, stdout=archive, timeout=90)
    if result.returncode:
        print("Device log archive is incomplete. Device files remain available.", file=sys.stderr)
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


def launch(phone, mode, output):
    # Refuse from current phone evidence before staging or launching anything.
    if audit(phone, output / "preflight.txt"):
        return 2
    if upload(phone, "install"):
        return 2
    shell = f"/system/bin/sh {STAGE}/oneios_switch.sh"
    check = phone.root(f"{shell} --framework-check {mode}", timeout=120)
    if check.returncode:
        return check.returncode
    baseline = status(phone)
    (output / "baseline.txt").write_text(baseline)
    boot = re.search(r"^boot=(.+)$", baseline, re.M).group(1)
    token = uuid.uuid4().hex
    if phone.root(f"""set -eu
umask 077
cd {STAGE}
mkdir -p launches
mkdir launches/{token}
/data/adb/ksu/bin/busybox setsid /system/bin/sh -c '
    {shell} --framework-session {mode} {ACK} {token}
    rc=$?
    printf "%s\n" "$rc" > launches/{token}/exit
' </dev/null > launches/{token}/switch.log 2>&1 &
""", timeout=10).returncode:
        return 2
    print(f"Framework {mode} requested. Recovery runs on the device.", flush=True)
    end = time.monotonic() + 1000
    with (output / "timeline.txt").open("w") as timeline:
        while time.monotonic() < end:
            try:
                state = status(phone, token)
                timeline.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n{state}\n")
                timeline.flush()
                current_boot = re.search(r"^boot=(.+)$", state, re.M).group(1)
                if current_boot != boot and "zygote=running" in state:
                    collect(phone, output)
                    print("Device rebooted during recovery. See the archived evidence.", file=sys.stderr)
                    return 4
                this_session = f"control/framework.launch={token}" in state
                if this_session and "control/state=returned" in state and "launch_exit=" in state:
                    collected = collect(phone, output)
                    restored = collected and restored_on_same_boot(baseline, state, mode)
                    print("Device reported an in-place return. Review the archived evidence." if restored
                          else "Recovery or phase verification failed. See the archived evidence.")
                    return 0 if restored else 4
                active = any(f"control/state={phase}" in state for phase in ("starting", "running", "returning"))
                if re.search(r"^launch_exit=[1-9]", state, re.M) and (not this_session or not active):
                    collect(phone, output)
                    return 4
            except (subprocess.SubprocessError, OSError) as error:
                timeline.write(f"ADB unavailable: {error}\n")
                timeline.flush()
            time.sleep(2)
    print("Device observation timed out. Recheck --status and retain the device logs.", file=sys.stderr)
    return 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("dry-run", "readiness", "recovery-smoke", "run", "return", "status", "storage-probe", "prepare", "collect"):
        modes.add_argument(f"--{mode}", dest="mode", action="store_const", const=mode)
    parser.add_argument("--confirm", action="store_true", help="Explicitly opt in to the requested device changes")
    parser.add_argument("--serial", help="ADB USB serial. Defaults to the sole authorized USB device.")
    parser.add_argument("--adb", type=Path, default=ADB_DEFAULT)
    parser.add_argument("--duration", type=int, choices=[240])
    parser.add_argument("--gpu", choices=["2d"])
    parser.add_argument("--bench-manifest", type=Path)
    parser.add_argument("--output", type=Path, help="New local evidence directory")
    args = parser.parse_args()
    if args.mode in {"recovery-smoke", "run", "storage-probe", "prepare"} and not args.confirm:
        parser.error(f"--{args.mode} requires --confirm")
    if args.mode != "run" and (args.duration or args.gpu):
        parser.error("--duration and --gpu apply to --run")
    if (args.mode == "prepare") != bool(args.bench_manifest):
        parser.error("--prepare requires --bench-manifest with an independently verified benchmark SHA-256 list")
    manifest = manifest_bytes(args.bench_manifest) if args.bench_manifest else None
    phone = Phone(args.adb, args.serial)
    if args.mode == "dry-run":
        return audit(phone)
    if args.mode == "status":
        print(status(phone), end="")
        return 0
    if args.mode == "return":
        return phone.root(f"if [ -f {STAGE}/oneios_switch.sh ]; then "
                          f"/system/bin/sh {STAGE}/oneios_switch.sh --framework-return; "
                          "else echo 'No experimental stage'; fi", timeout=650).returncode
    if args.mode in {"storage-probe", "prepare"}:
        return upload(phone, "probe" if args.mode == "storage-probe" else "prepare", manifest)

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
    return launch(phone, "smoke" if args.mode == "recovery-smoke" else "run", output)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"SM8850 takeover: {error}", file=sys.stderr)
        sys.exit(2)
