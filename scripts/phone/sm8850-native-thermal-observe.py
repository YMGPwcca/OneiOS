#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Observe the already tested native thermalctl across the existing 20s
Framework-only reboot smoke. No guest, new stop/return path or thermal writes.
The existing smoke owns admission and the deadline. Do not infer a working
vendor mitigation policy or independent recovery from one successful read.
"""
import argparse
import hashlib
from pathlib import Path
import re
import runpy
import shlex
import subprocess
import sys
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
TAKEOVER = runpy.run_path(str(HERE / "sm8850-takeover.py"))
STAGE = TAKEOVER["STAGE"]
SERVICES = ("thermal-engine", "vendor.samsung.hardware.thermal-default",
            "vendor.samsung.power-default", "poweropt-service", "perf2-hal-1-0")
HAL_SUMMARY = (r"^native-hal: schema=oneios\.native-thermal\.diagnostic\.v1 "
               r"clock=boottime start_ms=(\d+) end_ms=(\d+) "
               r"version=3 count=([1-9]\d*) status=OK native_max_severity=([0-6]) "
               r"diagnostic_only=1$")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def values(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def classify(text, phase, rc):
    """Separate actual reader results from phase/boot validity and smoke rc."""
    if (rc or text.splitlines().count("NATIVE_PROBE_BEGIN=" + phase) != 1 or
            text.splitlines().count("NATIVE_PROBE_END=" + phase) != 1):
        return "INCOMPLETE"
    if text.splitlines().count("NATIVE_RAW_RC=0") != 1:
        return "RAW_NOT_VERIFIED"
    if text.splitlines().count("NATIVE_HAL_RC=0") != 1:
        return "HAL_NOT_VERIFIED"
    summaries = re.findall(HAL_SUMMARY, text, re.M)
    if len(summaries) != 1:
        return "HAL_NOT_VERIFIED"
    start, end, count, _ = map(int, summaries[0])
    return "READERS_OK" if start <= end and 1 <= count <= 64 else "HAL_NOT_VERIFIED"


def probe_command(remote, digest, boot, phase, token="", generation="", deadline=""):
    require(re.fullmatch(r"/data/adb/\.oneios-natm\.[a-f0-9]{32}", remote),
            "invalid temporary path")
    require(re.fullmatch(r"[a-f0-9]{64}", digest), "invalid digest")
    require(re.fullmatch(r"[a-f0-9-]{36}", boot), "invalid boot ID")
    require(phase in ("ON", "OFF"), "invalid phase")
    ctl = shlex.quote(STAGE + "/control")
    session = shlex.quote(STAGE + "/session")
    if phase == "OFF":
        require(re.fullmatch(r"[a-f0-9]{32}", token), "invalid launch token")
        require(re.fullmatch(r"[a-f0-9.-]{1,95}", generation), "invalid generation")
        require(re.fullmatch(r"[0-9]{1,10}", deadline), "invalid deadline")
        phase_check = f"""
    [ "$(cat {ctl}/framework.launch)" = '{token}' ] &&
    [ "$(cat {ctl}/boot)" = '{boot}' ] &&
    [ "$(cat {ctl}/framework.mode)" = smoke ] &&
    [ "$(cat {ctl}/framework.duration)" = 20 ] &&
    [ "$(cat {ctl}/framework.return)" = reboot ] &&
    [ "$(cat {ctl}/state)" = running ] &&
    [ "$(cat {ctl}/framework.takeover-confirmed)" = '{generation}' ] &&
    [ "$(cat {ctl}/watchdog.generation)" = '{generation}' ] &&
    [ "$(cat {ctl}/framework.deadline)" = '{deadline}' ] &&
    [ ! -e {session}/return.request ] &&
    [ "$(getprop init.svc.zygote)" = stopped ] &&
    [ "$(getprop init.svc.zygote_next)" = stopped ] &&
    case "$(getprop init.svc.zygote_secondary)" in ''|stopped) true ;; *) false ;; esac &&
    ! pidof system_server >/dev/null 2>&1
"""
        remaining = f"""
remaining() {{
    read -r up rest < /proc/uptime || return 1
    tick=${{up%%.*}}
    [ '{deadline}' -ge "$((tick+$1))" ] &&
    [ '{deadline}' -le "$((tick+20))" ]
}}
"""
    else:
        phase_check = """
    [ "$(getprop sys.boot_completed)" = 1 ] &&
    [ "$(getprop init.svc.zygote)" = running ] &&
    pidof system_server >/dev/null 2>&1
"""
        remaining = "remaining() { return 0; }\n"
    return f"""set -u
umask 077
phase_valid() {{
    [ "$(id -u)" = 0 ] &&
    [ "$(getenforce)" = Enforcing ] &&
    [ "$(getprop ro.product.model)" = SM-S948B ] &&
    [ "$(getprop ro.product.device)" = m3q ] &&
    [ "$(getprop ro.soc.model)" = SM8850 ] &&
    case "$(getprop ro.build.display.id)" in *S948BXXS4BZIG*) true ;; *) false ;; esac &&
    [ "$(cat /proc/sys/kernel/random/boot_id)" = '{boot}' ] &&
    ! pidof xnuhost >/dev/null 2>&1 &&
    {phase_check.strip()}
}}
{remaining}
phase_valid && remaining 8 || exit 3
[ -d '{remote}' ] && [ ! -L '{remote}' ] &&
[ "$(stat -c '%u:%a' '{remote}')" = 0:700 ] &&
[ -f '{remote}/thermalctl' ] && [ ! -L '{remote}/thermalctl' ] &&
[ "$(stat -c '%u:%a' '{remote}/thermalctl')" = 0:700 ] &&
[ "$(sha256sum '{remote}/thermalctl' | cut -d' ' -f1)" = '{digest}' ] || exit 4
echo 'NATIVE_PROBE_BEGIN={phase}'
echo 'NATIVE_BOOT={boot}'
echo 'NATIVE_LAUNCH={token}'
echo 'NATIVE_GENERATION={generation}'
echo 'NATIVE_DEADLINE={deadline}'
id
for svc in {' '.join(SERVICES)}; do
    pid=$(getprop "init.svc_debug_pid.$svc")
    birth=unknown
    case "$pid" in
        ''|*[!0-9]*) ;;
        *) birth=$(sed 's/^.*) //' "/proc/$pid/stat" 2>/dev/null |
                   awk '$1!="Z" && $1!="X" && $20 ~ /^[0-9]+$/ {{print $20; exit}}') ;;
    esac
    printf 'native-service: name=%s state=%s pid=%s birth=%s\\n' "$svc" "$(getprop "init.svc.$svc")" "${{pid:-unknown}}" "${{birth:-unknown}}"
done
phase_valid && remaining 7 || exit 3
timeout -k 1 2 '{remote}/thermalctl' native-raw </dev/null
echo "NATIVE_RAW_RC=$?"
phase_valid && remaining 3 || exit 3
timeout -k 1 2 '{remote}/thermalctl' native-hal </dev/null
echo "NATIVE_HAL_RC=$?"
phase_valid && remaining 1 || exit 3
echo 'NATIVE_PROBE_END={phase}'
"""


def capture(phone, output, phase, command):
    try:
        p = phone.root(command, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=9)
        text = p.stdout.decode(errors="replace")
        rc = p.returncode
    except subprocess.TimeoutExpired as error:
        text = (error.stdout or b"").decode(errors="replace")
        rc = 124
    except (OSError, subprocess.SubprocessError) as error:
        text, rc = type(error).__name__ + "\n", 125
    (output / ("native-" + phase.lower() + ".log")).write_text(text)
    print(text, end="" if text.endswith("\n") else "\n", flush=True)
    result = classify(text, phase, rc)
    print("NATIVE_" + phase + "=" + result, "exit=" + str(rc), flush=True)
    return result


def run(args):
    data = args.thermalctl.read_bytes()
    require(0 < len(data) <= 16 * 1024 * 1024, "unexpected thermalctl size")
    require(re.fullmatch(r"[a-f0-9]{64}", args.sha256) and
            hashlib.sha256(data).hexdigest() == args.sha256, "local thermalctl hash mismatch")
    output = Path(tempfile.mkdtemp(prefix="oneios-native-off."))
    print("EVIDENCE=" + str(output), flush=True)
    phone = TAKEOVER["Phone"](args.adb, args.serial)
    initial = TAKEOVER["status"](phone)
    (output / "stock-status.txt").write_text(initial)
    boot = values(initial).get("boot", "")
    remote = "/data/adb/.oneios-natm." + uuid.uuid4().hex
    on_command = probe_command(remote, args.sha256, boot, "ON")
    off_result = "NOT_OBSERVED"
    # Root-private, unique temporary directory; receive only the checked
    # diagnostic executable. The existing launcher separately owns its stage.
    transfer = f"""set -eu
umask 077
[ "$(id -u)" = 0 ] && [ "$(getenforce)" = Enforcing ]
[ -d /data/adb ] && [ ! -L /data/adb ] &&
[ "$(stat -c '%u' /data/adb)" = 0 ]
case "$(stat -c '%A' /data/adb)" in ?????w*|????????w*) exit 3 ;; d?????????) ;; *) exit 3 ;; esac
mkdir '{remote}'
trap 'rm -f "{remote}/thermalctl"; rmdir "{remote}"' EXIT
cat > '{remote}/thermalctl'
chmod 700 '{remote}/thermalctl'
[ "$(sha256sum '{remote}/thermalctl' | cut -d' ' -f1)" = '{args.sha256}' ]
trap - EXIT
"""
    transferred = False
    try:
        p = phone.root(transfer, input=data, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=30)
        require(p.returncode == 0, "diagnostic transfer failed: " +
                p.stdout.decode(errors="replace"))
        transferred = True
        require(capture(phone, output, "ON", on_command) == "READERS_OK",
                "stock diagnostic incomplete; do not request Framework stop")

        def ready(p, state, expected_boot, token):
            nonlocal off_result
            kv = values(state)
            require(expected_boot == boot, "boot changed before smoke")
            cmd = probe_command(remote, args.sha256, boot, "OFF", token,
                                kv.get("control/framework.takeover-confirmed", ""),
                                kv.get("control/framework.deadline", ""))
            off_result = capture(p, output, "OFF", cmd)

        lifecycle = output / "existing-smoke"
        lifecycle.mkdir(mode=0o700)
        rc = TAKEOVER["launch"](phone, "smoke", lifecycle, reboot_only=True,
                                on_reboot_smoke_ready=ready, smoke_seconds=20)
        print("NATIVE_OFF_OBSERVATION=" + off_result, flush=True)
        print("EXISTING_SMOKE_EXIT=" + str(rc), flush=True)
        print("NATIVE_MITIGATION_AFTER_FRAMEWORK_OFF=NOT_QUALIFIED", flush=True)
        print("DEVICE_THERMAL_CONTROL_WRITES=NONE_BY_OBSERVER", flush=True)
        # Never reinterpret the old unqualified reboot receipt as success.
        return rc if rc else (0 if off_result == "READERS_OK" else 4)
    finally:
        if transferred:
            try:
                clean = phone.root(
                    f"[ -d '{remote}' ] && [ ! -L '{remote}' ] && "
                    f"""[ "$(stat -c '%u:%a' '{remote}')" = 0:700 ] && """
                    f"rm -f '{remote}/thermalctl' && rmdir '{remote}'",
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, timeout=8)
                if clean.returncode:
                    print("NATIVE_TEMP_CLEANUP=UNVERIFIED " + remote, flush=True)
            except (OSError, subprocess.SubprocessError):
                print("NATIVE_TEMP_CLEANUP=UNVERIFIED " + remote, flush=True)
        else:
            print("NATIVE_TEMP_TRANSFER_OR_CLEANUP=UNVERIFIED " + remote, flush=True)
        print("EVIDENCE=" + str(output), flush=True)


def self_test():
    summary = ("native-hal: schema=oneios.native-thermal.diagnostic.v1 clock=boottime "
               "start_ms=123 end_ms=124 version=3 count=6 status=OK native_max_severity=0 "
               "diagnostic_only=1")
    complete = "NATIVE_PROBE_BEGIN=OFF\nNATIVE_RAW_RC=0\n" + summary + \
               "\nNATIVE_HAL_RC=0\nNATIVE_PROBE_END=OFF\n"
    assert classify(complete, "OFF", 0) == "READERS_OK"
    assert classify(complete, "OFF", 124) == "INCOMPLETE"
    assert classify(complete, "ON", 0) == "INCOMPLETE"
    assert classify(complete.replace("NATIVE_PROBE_END=OFF", ""), "OFF", 0) == "INCOMPLETE"
    assert classify(complete.replace("NATIVE_RAW_RC=0", "NATIVE_RAW_RC=1"), "OFF", 0) == "RAW_NOT_VERIFIED"
    assert classify(complete.replace("NATIVE_HAL_RC=0", "NATIVE_HAL_RC=1"), "OFF", 0) == "HAL_NOT_VERIFIED"
    assert classify(complete.replace("version=3", "version=2"), "OFF", 0) == "HAL_NOT_VERIFIED"
    assert classify(complete.replace("end_ms=124", "end_ms=122"), "OFF", 0) == "HAL_NOT_VERIFIED"
    remote = "/data/adb/.oneios-natm." + "a"*32
    cmd = probe_command(remote, "b"*64, "c"*36, "OFF", "d"*32, "e"*32, "12345")
    assert "framework.takeover-confirmed" in cmd and "remaining 8" in cmd
    assert "init.svc.zygote_next" in cmd and "pidof system_server" in cmd
    assert "timeout -k 1 2" in cmd and "NATIVE_PROBE_END=OFF" in cmd
    subprocess.run(["sh", "-n"], input=cmd, text=True, check=True)
    subprocess.run(["sh", "-n"], input=probe_command(remote, "b"*64, "c"*36, "ON"),
                   text=True, check=True)
    print("NATIVE_OFF_OBSERVER_SELFTEST=PASS DEVICE_ACCESS=NONE")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--thermalctl", type=Path)
    ap.add_argument("--sha256")
    ap.add_argument("--adb", type=Path, default=TAKEOVER["ADB_DEFAULT"])
    ap.add_argument("--serial")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--accept-legacy-watchdog-risk", action="store_true",
                    help="existing 20s Framework-only smoke requests mandatory reboot")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not (args.confirm and args.accept_legacy_watchdog_risk and args.thermalctl and args.sha256):
        ap.error("requires the exact thermalctl/hash and explicit existing reboot-smoke consent")
    try:
        return run(args)
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print("NATIVE_OFF_OBSERVER=INCOMPLETE " + str(error), file=sys.stderr, flush=True)
        return 4


if __name__ == "__main__":
    sys.exit(main())
