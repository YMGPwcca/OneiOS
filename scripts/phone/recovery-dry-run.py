#!/usr/bin/env python3
"""Run the pinned OneOS recovery scripts against an isolated SM8850 fixture."""

import argparse
import errno
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


PINNED_FILES = {
    "switch": "switcher/assets/oneios_switch.sh",
    "return": "switcher/assets/oneios_return.sh",
    "phone-tools": "app-android/core/root/src/test/resources/oneios/phone-tools.sh",
}
FINGERPRINT = "oneios/phase3-fixture/m3q:17/PHASE3/0001:userdebug/test-keys"
COMPOSER = "vendor.qti.hardware.display.composer"
UDC = "a600000.dwc3"
SESSION = "data/local/tmp/oneios"
MOUNT = "1 0 8:1 / / rw - ext4 /dev/root rw\n"
STAGE_MOUNT = "40 1 254:50 /local/tmp/oneios /data rw - f2fs /dev/block/dm-50 rw\n"
CGROUP = "sys/fs/cgroup/oneios_session"
SHMEM = "sys/kernel/mm/transparent_hugepage/shmem_enabled"
TOKEN = "phase3-current"

# Fixture-only instrumentation. The Android tools still use the pinned
# OneOS test stubs. The controller releases virtual ticks on demand.
HOST_SHELL = """#!/bin/sh
case "$1" in "$ONEIOS_TEST_ROOT"/data/local/tmp/oneios/oneios_*.sh) ;; *) exit 99 ;; esac
entry="$ONEIOS_TEST_ROOT/proc/$$"
mkdir -p "$entry"
printf '%s\\0' "$@" > "$entry/cmdline"
exec "$PHASE3_SHELL" "$@"
"""

STEPPED_SLEEP = """#!/bin/sh
clock=$ONEIOS_TEST_ROOT/clock
if [ -f "$clock/step" ] && [ "$1" = "$(cat "$clock/step")" ]; then
    tick=$(cat "$clock/tick")
    printf '%s %s\\n' "$tick" "$PPID" >> "$clock/requests"
    while [ "$(cat "$clock/tick")" = "$tick" ]; do /usr/bin/sleep 0.01; done
    exit 0
fi
exec "$ONEIOS_TEST_ROOT/stubs/sleep" "$@"
"""

TRACED_CAT = """#!/bin/sh
/usr/bin/cat "$@"
rc=$?
case "$1" in
    "$ONEIOS_TEST_ROOT"/data/local/tmp/oneios/control/keys/down)
        echo read >> "$ONEIOS_TEST_ROOT/clock/down-reads" ;;
esac
exit "$rc"
"""


def wait_for(description, poll, seconds=12):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = poll()
        if value:
            return value
        time.sleep(0.01)
    raise RuntimeError(f"Timed out waiting for {description}")


class Fixture:
    def __init__(self, root, shell, early=False):
        self.root = root
        self.stage = root / SESSION
        self.control = self.stage / "control"
        self.session = self.stage / "session"
        self.clock = root / "clock"
        self.processes = []
        self.streams = []
        self.commands = []
        self.checks = []
        self.epoch = 0
        self.timer = None
        self.env = dict(os.environ, ONEIOS_TEST_ROOT=str(root), ONEIOS_TEST_SH=str(root / "host-sh"),
                        BB=str(root / "data/adb/ksu/bin/busybox"), PHASE3_SHELL=shell,
                        ONEIOS_RETURN_MAX="0", ONEIOS_TEST_STEP_K="80")
        for directory in ("bin", "stubs", "log", "pids", "services", "behave", "events", "keystate",
                          "clock", "sys/power", CGROUP, "proc/sys/kernel/random"):
            (root / directory).mkdir(parents=True)
        for kind in ("switch", "return"):
            self.write(f"{SESSION}/oneios_{kind}.sh", Path(f"/phone/source/{kind}").read_text())
        stub = Path("/phone/source/phone-tools").read_text().replace("@SLEEP@", "/usr/bin/sleep")
        for name in ("getprop", "setprop", "pidof", "service", "getenforce", "am", "vdc", "sync",
                     "renice", "lshal", "now", "kill", "getevent", "watchdog-stat", "watchdog-io"):
            self.executable(f"bin/{name}", stub)
        for name in ("busybox", "resetprop"):
            self.executable(f"data/adb/ksu/bin/{name}", stub)
        self.executable("bin/settings", "#!/bin/sh\n[ \"$*\" = 'get global adb_enabled' ] && echo 1\n")
        self.executable("bin/sleep", STEPPED_SLEEP)
        self.executable("stubs/sleep", stub)
        self.executable("bin/cat", TRACED_CAT)
        self.executable("host-sh", HOST_SHELL)
        self.write("sleep_scale", "30\n")
        self.write("clock/tick", "0\n")
        self.write("nextpid", "39000\n")
        self.write("selinux", "Enforcing\n")
        self.write("proc/1/mountinfo", MOUNT)
        self.write("proc/sys/kernel/random/boot_id", "phase3-boot\n")
        self.proc(1, "init")
        self.write("vendor/etc/vintf/manifest.xml", "<name>android.hardware.graphics.composer3</name>\n")
        props = {
            "ro.product.model": "SM-S948B", "ro.product.device": "m3q", "ro.soc.model": "SM8850",
            "ro.build.fingerprint": FINGERPRINT, "persist.sys.timezone": "Etc/UTC",
            "init.svc.zygote": "running" if early else "stopped", "init.svc.zygote_secondary": "stopped",
            "crashrecovery.rescue_boot_start": "7", f"init.svc_debug_pid.{COMPOSER}": "30311",
        }
        daemons = {
            "vold": (30300, "vold"), "keystore2": (30301, None), "servicemanager": (30302, None),
            "hwservicemanager": (30303, None), "logd": (30304, None), "lmkd": (30305, None),
            "installd": (30306, "installd"), "surfaceflinger": (30310, "SurfaceFlinger"),
            "composer": (30311, "android.hardware.graphics.composer3.IComposer/default"),
            "audioserver": (30312, "media.audio_policy"), "netd": (30313, None),
            "cameraserver": (30314, None),
        }
        if early:
            daemons.update(zygote64=(30320, None), system_server=(30321, None))
        for name, (pid, service) in daemons.items():
            self.proc(pid, name)
            self.write(f"pids/{name}", f"{pid}\n")
            props[f"init.svc.{COMPOSER if name == 'composer' else name}"] = "running"
            if service:
                self.write("services/" + service.replace("/", "_"), "")
        self.write("services/media.audio_flinger", "")
        self.write("props", "".join(f"{key}={value}\n" for key, value in props.items()))
        self.write("props", "crashrecovery.rescue_boot_start=29\n", append=True)
        for name, value in {
            "boot": "phase3-boot", "state": "starting" if early else "running", "keys/session": TOKEN,
            "base/boot_id": "phase3-boot", "base/selinux": "Enforcing", "base/mounts": "/",
            "base/pids": "vold 30300\nkeystore2 30301\nsurfaceflinger 30310\nservicemanager 30302",
            "base/props": "\n".join(f"[{key}]: [{value}]" for key, value in props.items()),
            "base/backlight": "", "base/shmem_enabled": "never",
        }.items():
            self.write(f"{SESSION}/control/{name}", value + "\n")
        self.write(SHMEM, "always within_size [advise] never deny force\n")
        self.write(f"{SESSION}/session/ready", "")
        self.write(f"{SESSION}/session/xnuhost.log", "fixture xnuhost\n")
        if not early:
            self.write(f"{SESSION}/control/stopped", "1\n")
            self.write(f"{SESSION}/control/xnuhost.pid", "35000\n")
            self.write(f"{SESSION}/control/mntns", "mnt:[82]\n")
            self.proc(35000, "xnuhost", ns="mnt:[82]", cgroup=True, mounted=True)
        self.write("input-devices", self.input_inventory())

    @staticmethod
    def input_inventory():
        return "".join(f'add device {i}: /dev/input/{event}\n  name: "{name}"\n  events:\n    KEY (0001): {keys}\n'
                       for i, (event, name, keys) in enumerate((
                           ("event12", "gpio-keys", "KEY_VOLUMEUP"),
                           ("event5", "pmic_resin", "KEY_VOLUMEDOWN"),
                           ("event2", "HUAWEI Band 11 Consumer Control", "KEY_VOLUMEUP KEY_VOLUMEDOWN"),
                           ("event3", "pmic_pwrkey", "KEY_POWER KEY_VOLUMEDOWN"),
                       ), 1))

    def write(self, name, value, append=False):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a" if append else "w") as output:
            output.write(value)

    def executable(self, name, value):
        self.write(name, value)
        (self.root / name).chmod(0o700)

    def proc(self, pid, command, *, ns="mnt:[1]", cgroup=False, mounted=False):
        directory = self.root / f"proc/{pid}"
        (directory / "ns").mkdir(parents=True)
        (directory / "ns/mnt").symlink_to(ns)
        (directory / "cmdline").write_bytes(command.replace(" ", "\0").encode() + b"\0")
        (directory / "comm").write_text(command.split()[0] + "\n")
        if cgroup:
            self.write(f"{CGROUP}/cgroup.procs", f"{pid}\n", append=True)
        if mounted:
            (directory / "mountinfo").write_text(MOUNT + STAGE_MOUNT)

    def read(self, path):
        try:
            return path.read_text().strip()
        except FileNotFoundError:
            return ""

    def start(self, script, *args):
        command = [str(self.root / "host-sh"), str(self.stage / f"oneios_{script}.sh"), *args]
        self.commands.append([f"oneios_{script}.sh", *args])
        output = self.root / f"log/command-{len(self.commands)}"
        with output.open("w") as stream:
            process = subprocess.Popen(command, env=self.env, stdin=subprocess.DEVNULL,
                                       stdout=stream, stderr=stream, start_new_session=True)
        self.processes.append((process, output))
        return process, output

    def run(self, script, *args):
        process, output = self.start(script, *args)
        return process.wait(20), self.read(output)

    def watcher(self):
        process, output = self.start("switch", "--watch")
        wait_for("watcher PID", lambda: self.read(self.control / "watcher.pid"))
        return process, output

    def readers(self):
        rc, selected = self.run("switch", "--key-devices")
        expected = ["/dev/input/event12", "/dev/input/event5"]
        self.check("production selector excludes wearable and power key", expected, selected.splitlines())
        if rc or selected.splitlines() != expected:
            raise RuntimeError("Cannot start readers without a validated selected pair")
        return selected.splitlines()

    def events(self, nodes):
        for node, role in zip(nodes, ("up", "down")):
            fifo = self.root / "events" / Path(node).name
            os.mkfifo(fifo, 0o600)
            self.start("switch", "--keys", node, TOKEN, role)
            def connect():
                try:
                    # Return a file object so descriptor number 0 can't be
                    # mistaken for a failed poll.
                    return os.fdopen(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK), "w", buffering=1)
                except OSError as error:
                    if error.errno != errno.ENXIO:
                        raise
                    return None
            self.streams.append(wait_for(f"{role} event stream", connect))

    def emit(self, role, value):
        index, key = (0, "KEY_VOLUMEUP") if role == "up" else (1, "KEY_VOLUMEDOWN")
        self.streams[index].write(f"EV_KEY {key} {value}\n")
        wait_for(f"{role} {value}", lambda: self.read(self.control / f"keys/{role}") == value)

    def wait_tick(self):
        def sleeping():
            for line in self.read(self.clock / "requests").splitlines():
                epoch, pid = line.split()
                if int(epoch) == self.epoch and self.timer in (None, int(pid)):
                    return int(pid)
            return None
        self.timer = wait_for(f"virtual sleep at tick {self.epoch}", sleeping)

    def ticks(self, count):
        for _ in range(count):
            self.wait_tick()
            self.epoch += 1
            temporary = self.clock / "next"
            temporary.write_text(f"{self.epoch}\n")
            temporary.replace(self.clock / "tick")
        return self.timer

    def start_chord(self):
        self.write("clock/step", "0.25\n")
        self.events(self.readers())
        self.emit("up", "DOWN")
        wait_for("up reader evaluated the other key", lambda: self.read(self.clock / "down-reads"))
        self.emit("down", "DOWN")

    def check(self, label, expected, actual):
        self.checks.append({"check": label, "expected": expected, "actual": actual,
                            "status": "PASS" if actual == expected else "FAIL"})

    def request(self):
        return self.read(self.session / "return.request")

    def log(self, name):
        return self.read(self.root / "log" / name).splitlines()

    def outcome(self):
        return self.read(self.stage / "return.outcome")

    def return_log(self):
        return self.read(self.stage / "return.log")

    def properties(self):
        return dict(line.split("=", 1) for line in self.read(self.root / "props").splitlines())

    def success(self):
        self.check("return state", "returned", self.read(self.control / "state"))
        self.check("outcome", "inplace", self.outcome().split(" ", 1)[0])
        self.check("successful gates and stable unlock", [True] * 3, [
            fragment in self.return_log() for fragment in
            ("Gate A: no session process", "Gate B: display, audio", "user 0 unlocked")
        ])
        self.check("mock reboot requests", [], [line for line in self.log("setprop") if line.startswith("sys.powerctl ")])

    def failsafe(self, reason, framework_started=False):
        self.check("failsafe reason", True, self.outcome().startswith("failsafe ") and reason in self.return_log())
        self.check("framework startup attempted", framework_started, "ctl.restart netd" in self.log("setprop"))
        self.check("mock reboot request", True, "sys.powerctl reboot,oneios-inplace-failsafe" in self.log("setprop"))

    def close(self):
        for stream in self.streams:
            stream.close()
        # These process groups were created inside this case's sandbox.
        # No script kill() is forwarded to a real process by the phone stub.
        for process, _ in self.processes:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for process, _ in self.processes:
            process.wait(5)


def event_chord_and_watcher(f):
    watcher, output = f.watcher()
    f.start_chord()
    f.ticks(11)
    f.check("no request before the 3 s tick", "", f.request())
    f.ticks(1)
    f.check("watcher exit", 0, watcher.wait(20))
    f.check("event timer delivered the request", True, "held 3 s" in f.request())
    f.success()
    # The same request file is still present after return. A late watcher
    # observes returned and does not run the return path again.
    replay, replay_output = f.watcher()
    f.check("late watcher exits", 0, replay.wait(10))
    f.check("stale request left alone", True, "return is under way or done" in f.read(replay_output))
    f.check("watcher deliveries", 1, f.read(output).count("watcher: return asked"))
    f.check("framework restart count", 1, f.log("setprop").count("ctl.restart netd"))


def single_key_without_accessory(f):
    nodes = f.readers()
    f.events(nodes)
    f.emit("up", "DOWN")
    wait_for("one key evaluated", lambda: f.read(f.clock / "down-reads"))
    f.check("no request from one key", "", f.request())
    f.check("second key state remains unset", "", f.read(f.control / "keys/down"))


def brief_bounce(f):
    f.write(f"{SESSION}/control/state", "returning\n")
    f.start_chord()
    f.ticks(4)
    f.wait_tick()
    f.emit("down", "UP")
    f.ticks(1)
    # Confirm the timer actually sampled the release before restoring DOWN.
    f.wait_tick()
    f.emit("down", "DOWN")
    f.ticks(6)
    f.check("brief bounce does not trigger an early request", "", f.request())
    f.ticks(1)
    wait_for("request after 3 s with a brief bounce", f.request)
    f.check("brief bounce is tolerated", True, "held 3 s" in f.request())


def premature_release(f):
    f.start_chord()
    f.ticks(4)
    f.wait_tick()
    f.emit("down", "UP")
    timer = f.ticks(2)
    wait_for("cancelled hold timer exits", lambda: not Path(f"/proc/{timer}/stat").exists()
             or ") Z " in f.read(Path(f"/proc/{timer}/stat")))
    f.check("release before 3 s cancels the request", "", f.request())


def polling_after_watcher_death(f):
    watcher, _ = f.watcher()
    # Stop only this disposable local watcher, inside the sandbox.
    os.killpg(watcher.pid, signal.SIGKILL)
    f.check("watcher terminated abnormally", -signal.SIGKILL, watcher.wait(5))
    nodes = f.readers()
    for node, key in zip(nodes, ("KEY_VOLUMEUP", "KEY_VOLUMEDOWN")):
        f.write(f"keystate/{Path(node).name}", f"    KEY (0001): {key}*\n")
    f.write("clock/step", "0.5\n")
    reader, _ = f.start("switch", "--keys-poll", TOKEN, *nodes)
    f.ticks(5)
    f.check("polling waits for 3 s", "", f.request())
    f.ticks(1)
    wait_for("polled request", f.request)
    # Recovery also sleeps for half a second between service checks.
    (f.clock / "step").unlink()
    wait_for("direct key fallback", lambda: f.read(f.control / "state") == "returned", 20)
    f.check("polling delivered the request", True, "(polled)" in f.request())
    f.check("direct fallback path ran once", 1, f.return_log().count("=== Return to One UI (keys-direct)"))
    f.success()
    f.check("polling process exits", 0, reader.wait(10))


def watcher_without_return_script(f):
    (f.stage / "oneios_return.sh").unlink()
    watcher, _ = f.watcher()
    f.write(f"{SESSION}/session/return.request", "fixture request\n")
    f.check("watcher failure exit", 1, watcher.wait(12))
    f.check("mock watcher fallback", ["sys.powerctl reboot,oneios-watcher-failsafe"], f.log("setprop"))


def lost_feeder(f):
    f.write(f"{SESSION}/control/watchdog.target", "watchdog0 f2:0\n")
    f.write(f"{SESSION}/control/feeder.ready", "36000\n")
    f.write(f"{SESSION}/control/feeder.pid", "36000\n")
    f.proc(36000, "sh oneios_switch.sh --feed")
    watcher, output = f.watcher()
    wait_for("watcher acquired the wake lock", lambda: f.read(f.root / "sys/power/wake_lock") == "oneios_session")
    shutil.rmtree(f.root / "proc/36000")
    f.check("lost feeder causes watcher failure", 1, watcher.wait(15))
    f.check("feeder failure creates a request", True, f.request().startswith("watchdog feeder failed:"))
    f.check("feeder readiness invalidated", "", f.read(f.control / "feeder.ready"))
    f.check("watchdog I/O calls", [], f.log("watchdog"))
    f.check("watcher delivered the watchdog failure once", 1, f.read(output).count("watcher: watchdog feeder failed;"))
    f.check("unverified handoff did not start framework", False, "ctl.restart netd" in f.log("setprop"))


def stale_lock_and_watch_race(f):
    f.proc(36001, "unrelated-process")
    f.write(f"{SESSION}/control/returning.lock/pid", "36001\n")
    f.write(f"{SESSION}/control/display.pid", "36001\n")
    f.write("behave/hang_ctl.restart_netd", "")
    watcher, _ = f.watcher()
    f.write(f"{SESSION}/session/return.request", "fixture race\n")
    wait_for("watcher return holds lock and reached fake netd", lambda: "ctl.restart netd" in f.log("setprop"))
    rc, output = f.run("return", "manual")
    f.check("concurrent return exits", 0, rc)
    f.check("concurrent return defers to real lock owner", True, "another return is already running" in output)
    f.write("behave/unhang", "")
    f.check("watcher finishes", 0, watcher.wait(15))
    f.check("stale lock reclaimed", True, "is gone (pid '36001')" in f.return_log())
    f.check("unrelated PID survived", True, (f.root / "proc/36001").exists())
    f.check("framework restart count", 1, f.log("setprop").count("ctl.restart netd"))
    f.success()


def pid_fallback_usb_and_baseline(f):
    for pid, ns, cgroup, mounted in (
        (35001, "mnt:[1]", True, False),
        (35002, "mnt:[82]", False, False),
        (35003, "mnt:[83]", False, True),
    ):
        f.proc(pid, "surviving-task", ns=ns, cgroup=cgroup, mounted=mounted)
    f.write("props", f"sys.usb.config=adb\nsys.usb.state=adb\nsys.usb.controller={UDC}\ninit.svc.adbd=running\n", append=True)
    f.write(f"sys/class/udc/{UDC}/state", "configured\n")
    f.write("config/usb_gadget/g1/UDC", UDC + "\n")
    f.write(f"{SESSION}/usb-repair", "")
    f.check("save USB baseline exit", 0, f.run("switch", "--usb-save")[0])
    f.write("props", "sys.usb.config=mtp\nsys.usb.state=mtp\ninit.svc.adbd=stopped\n", append=True)
    f.write("config/usb_gadget/g1/UDC", "")
    f.check("normal return exit", 0, f.run("return", "manual")[0])
    f.success()
    f.check("cgroup.kill absent", False, (f.root / CGROUP / "cgroup.kill").exists())
    f.check("PID cleanup from cgroup, namespace, and stage mounts", [True] * 3,
            [f"-9 {pid}" in f.log("kill") and not (f.root / f"proc/{pid}").exists() for pid in (35001, 35002, 35003)])
    f.check("shmem mode restored", "never", f.read(f.root / SHMEM))
    f.check("shmem baseline cleared", False, (f.control / "base/shmem_enabled").exists())
    f.check("persist property preserved", "Etc/UTC", f.properties()["persist.sys.timezone"])
    f.check("boot counter restored", "7", f.properties()["crashrecovery.rescue_boot_start"])
    f.check("USB binding restored", UDC, f.read(f.root / "config/usb_gadget/g1/UDC"))
    commands = f.log("setprop")
    f.check("USB and adbd restored before netd", True,
            all(entry in commands and commands.index(entry) < commands.index("ctl.restart netd")
                for entry in ("sys.usb.config adb", "ctl.start adbd")))


def early_return_with_stale_stop_lock(f):
    f.write(f"{SESSION}/control/stop.lock/switch", "36001\n")
    f.check("early return exit", 0, f.run("return", "manual")[0])
    f.check("framework left running", "30321", f.read(f.root / "pids/system_server"))
    f.check("abandoned stop lock detected", True, "gone before the stop" in f.return_log())
    f.check("no init commands or simulated reboot", [], f.log("setprop"))
    f.check("early shmem restored", "never", f.read(f.root / SHMEM))


def gate_a_failure(f):
    f.proc(35001, "lingering-task", ns="mnt:[82]", cgroup=True)
    f.write("proc/35001/unkillable", "")
    f.check("return exit", 1, f.run("return", "manual")[0])
    f.failsafe("processes still in the session's namespace or cgroup")


def gate_b_failure(f):
    f.write(f"behave/no_restart_{COMPOSER}", "")
    f.check("return exit", 1, f.run("return", "manual")[0])
    f.failsafe("display composer " + COMPOSER + " did not restart")


def gate_c_failure(f):
    f.write("behave/no_system_server", "")
    f.check("return exit", 1, f.run("return", "manual")[0])
    f.failsafe("system_server did not start", framework_started=True)


CASES = (
    event_chord_and_watcher, single_key_without_accessory, brief_bounce, premature_release,
    polling_after_watcher_death, watcher_without_return_script, lost_feeder, stale_lock_and_watch_race,
    pid_fallback_usb_and_baseline, early_return_with_stale_stop_lock,
    gate_a_failure, gate_b_failure, gate_c_failure,
)


def worker(shell, definition):
    if Path.cwd() != Path("/phone") or not Path("/phone/source").is_dir() or os.geteuid() == 0:
        raise RuntimeError("Recovery cases require the unprivileged /phone sandbox")
    with tempfile.TemporaryDirectory(prefix="fixture-", dir="/phone") as temp:
        fixture = Fixture(Path(temp), shell, early=definition is early_return_with_stale_stop_lock)
        try:
            definition(fixture)
        except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError) as error:
            fixture.check("fixture completed", "normal completion", str(error))
        finally:
            fixture.close()
        failed = any(check["status"] == "FAIL" for check in fixture.checks)
        return {
            "case": definition.__name__, "shell": Path(shell).name, "scope": "simulation",
            "status": "FAIL" if failed else "PASS", "checks": fixture.checks, "commands": fixture.commands,
            "actual": {"request": fixture.request(), "released_ticks": fixture.epoch,
                       "outcome": fixture.outcome(), "return_log": fixture.return_log(),
                       "setprop": fixture.log("setprop"), "mock_kill": fixture.log("kill"),
                       "process_logs": [fixture.read(output) for _, output in fixture.processes] if failed else []},
        }


def git(*args):
    return subprocess.check_output(["git", *args], cwd=Path(__file__).resolve().parents[2])


def sandbox(path, shell, definition):
    return [
        "bwrap", "--unshare-all", "--die-with-parent", "--clearenv", "--setenv", "PATH", "/usr/bin",
        "--setenv", "LC_ALL", "C", "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib", "/lib64",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--bind", str(path), "/phone",
        "--chdir", "/phone", "/usr/bin/python3", "runner.py", "--worker", shell, definition.__name__,
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mksh", default=os.environ.get("ONEOS_TEST_MKSH") or shutil.which("mksh"))
    parser.add_argument("--observer-report", type=Path, help="Link a separately collected passive S26 JSON snapshot")
    parser.add_argument("--case", action="append", choices=[case.__name__ for case in CASES],
                        help="Run selected cases in both shells")
    args = parser.parse_args()
    if os.geteuid() == 0 or not shutil.which("bwrap") or not args.mksh or not os.access(args.mksh, os.X_OK):
        parser.error("requires non-root CachyOS with bwrap and an executable mksh (use --mksh)")
    pin = git("ls-tree", "HEAD", "app").decode().split()[2]
    if git("-C", "app", "rev-parse", "HEAD").decode().strip() != pin or git("diff", "--cached", "--name-only", "--", "app"):
        parser.error("the app checkout and index must match the parent gitlink")
    observation = None
    if args.observer_report:
        try:
            raw = args.observer_report.read_bytes()
            observation = json.loads(raw)
            firmware = observation["firmware"]
            if (observation["scope"] != "physical-passive" or
                    [firmware[k] for k in ("model", "device", "soc", "android")] !=
                    ["SM-S948B", "m3q", "SM8850", "17"] or
                    not isinstance(firmware["fingerprint"], str) or not firmware["fingerprint"]):
                parser.error("the passive report must contain an exact S26 target and readable fingerprint")
            observation["sha256"] = hashlib.sha256(raw).hexdigest()
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.error(f"cannot read passive observer report: {error}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    selected = [case for case in CASES if args.case is None or case.__name__ in args.case]
    with args.output.open("x") as report, tempfile.TemporaryDirectory(prefix="oneios-recovery-") as temp:
        path = Path(temp)
        (path / "source").mkdir()
        hashes = {}
        for label, name in PINNED_FILES.items():
            payload = git("-C", "app", "show", f"{pin}:{name}")
            (path / "source" / label).write_bytes(payload)
            hashes[name] = hashlib.sha256(payload).hexdigest()
        shutil.copyfile(__file__, path / "runner.py")
        shutil.copy2(args.mksh, path / "mksh")
        tests = []
        versions = {}
        for shell in ("/usr/bin/bash", "/phone/mksh"):
            version_command = sandbox(path, shell, CASES[0])[:-5] + [
                shell, "-c", 'echo "${BASH_VERSION:-$KSH_VERSION}"; test "$(id -u)" -ne 0',
            ]
            try:
                versions[Path(shell).name] = subprocess.check_output(version_command, text=True, timeout=10).strip()
            except (subprocess.SubprocessError, OSError) as error:
                versions[Path(shell).name] = str(error)
                for definition in selected:
                    tests.append({"case": definition.__name__, "shell": Path(shell).name, "scope": "simulation",
                                  "status": "BLOCKED", "expected": "unprivileged isolated shell", "actual": str(error)})
                continue
            for definition in selected:
                try:
                    outcome = subprocess.run(sandbox(path, shell, definition), capture_output=True, text=True, timeout=40)
                    if outcome.returncode:
                        raise RuntimeError(outcome.stderr.strip())
                    case = json.loads(outcome.stdout)
                except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as error:
                    case = {"case": definition.__name__, "shell": Path(shell).name, "scope": "simulation",
                            "status": "FAIL", "expected": "completed fixture evidence", "actual": str(error)}
                tests.append(case)
                print(f"{case['shell']}\t{case['status']}\t{case['case']}", flush=True)
        data = {
            "schema_version": 1, "timestamp_utc": datetime.now(timezone.utc).isoformat(), "scope": "simulation",
            "parent_base_commit": git("rev-parse", "HEAD").decode().strip(), "oneos_gitlink": pin,
            "sha256": hashes, "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "shell_versions": versions, "fixture_fingerprint": FINGERPRINT, "cases": tests,
            "target": {"model": "SM-S948B", "device": "m3q", "soc": "SM8850", "build": "S948BXXS4BZIG",
                       "firmware_fingerprint": None, "fingerprint_status": "BLOCKED", "source": "no live snapshot in this run"},
            "physical_checks": [
                {"check": "USB ADB and simultaneous Volume Up/Down", "status": "PASS",
                 "expected": "USB transport and chord observed with One UI running",
                 "actual": "Previously confirmed by the owner", "provenance": "owner supplied, not rerun"},
                {"check": "physical watchdog handoff and return Gates A/B/C", "status": "BLOCKED",
                 "expected": "Independent physical recovery acceptance", "actual": "Simulation only"},
                {"check": "boot a verified iOS image on SM8850", "status": "BLOCKED",
                 "expected": "Authorized switch with a verified image set", "actual": "No verified image set or authorization"},
            ],
        }
        if observation:
            data["target"].update(build=observation["firmware"]["build"],
                                  firmware_fingerprint=observation["firmware"]["fingerprint"],
                                  fingerprint_status="PASS", source="separate passive observer report")
            data["passive_observation"] = {"sha256": observation["sha256"], "checks": observation["checks"]}
        json.dump(data, report, indent=2)
        report.write("\n")
    print(args.output)
    return 0 if all(case["status"] == "PASS" for case in tests) else 1


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        fn = next(definition for definition in CASES if definition.__name__ == sys.argv[3])
        print(json.dumps(worker(sys.argv[2], fn)))
    else:
        raise SystemExit(main())
