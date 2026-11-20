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
[ "$2" != --guard ] || [ ! -e "$ONEIOS_TEST_ROOT/behave/native-guard-unavailable" ] || exit 3
if [ "$2" = --watchdog-probe ] && [ -e "$ONEIOS_TEST_ROOT/behave/native-watchdog-probe" ]; then
    [ -s "$ONEIOS_TEST_ROOT/pids/system_server" ] || exit 2
    echo "watchdog0 f2:0"
    exit 0
fi
entry="$ONEIOS_TEST_ROOT/proc/$$"
mkdir -p "$entry"
printf '%s\\0' "$@" > "$entry/cmdline"
/usr/bin/cat "/proc/$$/stat" > "$entry/stat"
exec "$PHASE3_SHELL" "$@"
"""

STEPPED_SLEEP = """#!/bin/sh
clock=$ONEIOS_TEST_ROOT/clock
if [ -f "$clock/step" ] && [ "$1" = "$(cat "$clock/step")" ]; then
    tick=$(cat "$clock/tick")
    printf '%s %s\\n' "$tick" "$PPID" >> "$clock/requests"
    while [ -f "$clock/step" ] && [ "$(cat "$clock/tick")" = "$tick" ]; do /usr/bin/sleep 0.01; done
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
    "$ONEIOS_TEST_ROOT"/sys/class/watchdog/watchdog0/timeleft)
        echo read >> "$ONEIOS_TEST_ROOT/clock/timeleft-reads" ;;
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
            original = Path(f"/phone/source/{kind}").read_text()
            shebang, separator, body = original.partition("\n")
            if not separator or not shebang.startswith("#!"):
                raise RuntimeError("Unexpected pinned OneOS script header")
            # Fixture-only instrumentation: mksh R59 has cat/sleep
            # builtins that bypass the PATH-based test doubles.
            instrumentation = (
                'cat() { "$ONEIOS_TEST_ROOT/bin/cat" "$@"; }\n'
                'sleep() { "$ONEIOS_TEST_ROOT/bin/sleep" "$@"; }\n'
            )
            self.write(
                f"{SESSION}/oneios_{kind}.sh",
                shebang + "\n" + instrumentation + body,
            )
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
        self.write("proc/uptime", "100.00 0.00\n")
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
        (directory / "stat").write_text(f"{pid} (fixture) S " + "0 " * 18 + "800\n")
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
    watchdog_fixture_ready(f)
    watcher, output = f.watcher()
    wait_for("watcher acquired the wake lock", lambda: f.read(f.root / "sys/power/wake_lock") == "oneios_session")
    shutil.rmtree(f.root / "proc/4500")
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


def watchdog_fixture(f, *, supported=True):
    if supported:
        # Exercise the pinned S24-only control flow against fake files.
        f.write("props", "ro.product.model=SM-S928B\nro.product.device=e3q\nro.soc.model=SM8650\n", append=True)
    f.write("dev/watchdog", "a:82\n")
    f.write("dev/watchdog0", "f2:0\n")
    f.write("sys/class/misc/watchdog/dev", "10:130\n")
    for name, value in {"dev": "242:0", "identity": "Software Watchdog", "state": "active", "timeout": "100"}.items():
        f.write(f"sys/class/watchdog/watchdog0/{name}", value + "\n")
    f.write(f"{SESSION}/control/watchdog.target", "watchdog0 f2:0\n")
    f.write(f"{SESSION}/control/watchdog.generation", "fixture-watchdog\n")
    f.write(f"{SESSION}/control/feeder.arm", "fixture-watchdog 100\n")


def watchdog_s26_refused(f):
    watchdog_fixture(f, supported=False)
    f.check("SM8850 feeder refused", 3, f.run("switch", "--watchdog-test", "feed")[0])
    f.check("no simulated watchdog I/O", [], f.log("watchdog"))
    f.check("no readiness published", False, (f.control / "feeder.ready").exists())
    f.check("no Android property commands", [], f.log("setprop"))


def watchdog_fault(f, fault, expected_io):
    watchdog_fixture(f)
    f.write(f"behave/{fault}", "")
    f.check("fake feeder exit", 4, f.run("switch", "--watchdog-test", "feed")[0])
    f.check("bounded open/ping sequence", expected_io, f.log("watchdog"))
    f.check("readiness withdrawn", False, (f.control / "feeder.ready").exists())
    f.check("recovery request written", True, f.request().startswith("watchdog feeder failed:"))
    f.check("fake return exit", 1, f.run("return", "manual")[0])
    f.failsafe("watchdog feeder failed")


def watchdog_exclusive_open_busy(f):
    watchdog_fault(f, "watchdog_busy", ["open watchdog0"])


def watchdog_ping_fails_after_first_success(f):
    watchdog_fault(f, "watchdog_ping_fails", ["open watchdog0", "ping .", "ping ."])


def watchdog_fixture_ready(f):
    watchdog_fixture(f)
    f.write(f"{SESSION}/control/feeder.pid", "4500\n")
    f.write(f"{SESSION}/control/feeder.ready", "4500\n")
    f.proc(4500, "sh oneios_switch.sh --feed")
    f.write(f"{SESSION}/control/feeder.heartbeat", "fixture-watchdog 4500 800 100\n")


def watchdog_stuck_feeder(f):
    watchdog_fixture_ready(f)
    f.write("proc/4500/unkillable", "")
    f.write("clock/step", "1\n")
    watcher, _ = f.watcher()
    f.ticks(3)
    f.wait_tick()
    f.check("feeder has not timed out at the same monotonic second", "", f.request())
    f.write("proc/uptime", "105.00 0.00\n")
    (f.clock / "step").unlink()
    f.check("stall requests recovery without an external request", True, bool(wait_for("automatic stall request", f.request, 2)))
    f.check("watcher returns through simulated failsafe", 1, watcher.wait(15))
    f.failsafe("watchdog feeder failed")
    f.check("lost progress diagnosed", True, "keepalive progress stalled" in f.request())
    f.check("feeder still cannot be removed", True, (f.root / "proc/4500").exists())


def watchdog_handoff_order(f):
    watchdog_fixture_ready(f)
    f.write("behave/watchdog_exclusive_handoff", "")
    f.check("fake return exit", 0, f.run("return", "manual")[0])
    f.success()
    log = f.return_log()
    f.check("release before framework restart", True,
            0 <= log.find("watchdog feeder released") < log.find("One UI's zygote started"))
    f.check("observed fixture reacquisition", True, "watchdog ownership confirmed" in log)
    f.check("no transfer-side simulated watchdog I/O", [], f.log("watchdog"))
    f.check("normal shutdown does not report feeder failure", False, (f.control / "feeder.failed").exists())


def watchdog_framework_never_reacquires(f):
    watchdog_fixture_ready(f)
    f.write("behave/watchdog_no_reacquire", "")
    f.check("fake return exit", 1, f.run("return", "manual")[0])
    f.failsafe("system_server did not reacquire the watchdog", framework_started=True)
    f.check("no in-place success despite running framework", False, f.outcome().startswith("inplace "))


def watchdog_invalid_heartbeat(f):
    watchdog_fixture_ready(f)
    for label, record in (
        ("future", "fixture-watchdog 4500 800 101"),
        ("stale generation", "old-watchdog 4500 800 100"),
        ("invalid timestamp", "fixture-watchdog 4500 800 -1"),
        ("overflow", "fixture-watchdog 4500 800 99999999999999999"),
        ("before arm", "fixture-watchdog 4500 800 99"),
        ("missing", None),
    ):
        if record is None:
            (f.control / "feeder.heartbeat").unlink()
        else:
            f.write(f"{SESSION}/control/feeder.heartbeat", record + "\n")
        f.check(label + " heartbeat rejected", 2, f.run("switch", "--watchdog-health")[0])
    f.write(f"{SESSION}/control/feeder.heartbeat", "fixture-watchdog 4500 800 100\n")
    f.write("proc/4500/stat", "4500 (same command line) S " + "0 " * 18 + "801\n")
    f.check("reused PID with same command rejected", 2, f.run("switch", "--watchdog-health")[0])
    f.write(f"{SESSION}/control/feeder.off", "")
    f.check("normal close is inactive", 1, f.run("switch", "--watchdog-health")[0])


def block_fixture_ping(f, when):
    f.write("behave/hold_ping", when + "\n")
    (f.root / "bin/watchdog-io").rename(f.root / "stubs/watchdog-io")
    f.executable("bin/watchdog-io", """#!/bin/sh
root=$ONEIOS_TEST_ROOT
if [ "$1" = ping ] && { [ "$(cat "$root/behave/hold_ping")" = first ] ||
                        [ -e "$root/behave/watchdog_pinged" ]; }; then
    touch "$root/behave/ping_entered"
    while [ ! -e "$root/behave/ping_released" ]; do /usr/bin/sleep 0.01; done
fi
exec "$root/stubs/watchdog-io" "$@"
""")


def watchdog_delayed_first_ping(f):
    watchdog_fixture(f)
    block_fixture_ping(f, "first")
    feeder, _ = f.start("switch", "--watchdog-test", "feed")
    wait_for("mock first keepalive entered", lambda: (f.root / "behave/ping_entered").exists())
    f.check("in-flight keepalive publishes no heartbeat", False, (f.control / "feeder.heartbeat").exists())
    f.check("first-ping window still open", 1, f.run("switch", "--watchdog-health")[0])
    f.write("proc/uptime", "103.00 0.00\n")
    f.check("first-ping deadline exceeded", 2, f.run("switch", "--watchdog-health")[0])
    f.write("behave/ping_released", "")
    f.check("late first ping is rejected", 4, feeder.wait(8))
    f.check("no heartbeat after late first ping", False, (f.control / "feeder.heartbeat").exists())
    f.check("late first success requests recovery", True, "first keepalive missed its deadline" in f.request())


def watchdog_blocked_second_ping(f):
    watchdog_fixture(f)
    block_fixture_ping(f, "after_first")
    feeder, _ = f.start("switch", "--watchdog-test", "feed")
    wait_for("mock second keepalive blocked", lambda: (f.root / "behave/ping_entered").exists())
    last = f.read(f.control / "feeder.heartbeat")
    f.check("first successful ping is fresh", 0, f.run("switch", "--watchdog-health")[0])
    f.check("heartbeat contains completed first ping", "100", last.split()[-1])
    f.write("proc/uptime", "105.00 0.00\n")
    watcher, _ = f.watcher()
    f.check("watcher initiated simulated failsafe", 1, watcher.wait(15))
    f.check("blocked write did not publish progress", last, f.read(f.control / "feeder.heartbeat"))
    f.check("feeder still alive on stall", None, feeder.poll())
    f.check("automatic stall reason", True, "keepalive progress stalled" in f.request())
    f.failsafe("watchdog feeder failed")
    f.write("behave/ping_released", "")
    f.check("late keepalive cannot make the feeder healthy again", 4, feeder.wait(8))
    f.check("late completion does not overwrite the heartbeat", last, f.read(f.control / "feeder.heartbeat"))


def watchdog_guard_supervises_a_return(f):
    watchdog_fixture_ready(f)
    f.write(f"{SESSION}/control/state", "returning\n")
    f.write(f"{SESSION}/control/return.guard", "fixture-guard\n")
    f.write("proc/uptime", "105.00 0.00\n")
    guard, _ = f.start("return", "--guard", "fixture-guard")
    wait_for("return guard requested recovery", f.request)
    f.check("return guard records stalled progress", True, "keepalive progress stalled" in f.request())
    (f.control / "return.guard").unlink()
    f.check("disarmed guard exits quietly", 0, guard.wait(5))
    f.check("guard did not start a second return", [], f.log("setprop"))


def watchdog_concurrent_recovery(f):
    watchdog_fixture_ready(f)
    f.write("proc/uptime", "106.00 0.00\n")
    f.write(f"{SESSION}/session/return.request", "existing independent recovery request\n")
    stale, _ = f.start("switch", "--watchdog-supervise", "old-watchdog")
    f.check("superseded supervisor exits quietly", 1, stale.wait(5))
    f.check("old generation did not record a fault", False, (f.control / "feeder.failed").exists())
    f.check("late watcher cannot return a new generation", 0, f.run("return", "watcher", "old-watchdog")[0])
    f.check("no init commands by the late watcher", [], f.log("setprop"))
    supervisors = [f.start("switch", "--watchdog-supervise", "fixture-watchdog")[0] for _ in range(2)]
    f.check("both supervisors detect the fault", [0, 0], [p.wait(5) for p in supervisors])
    f.check("one failure diagnostic", 1, f.read(f.control / "watchdog_feeder.log").count("progress stalled"))
    f.check("earlier request is preserved", "existing independent recovery request", f.request())


def framework_setup(f):
    f.env["ONEIOS_TEST_FRAMEWORK"] = "1"
    f.write(f"{SESSION}/control/base/framework_services",
            f"surfaceflinger 30310\n{COMPOSER} 30311\n")
    f.write("props", "init.svc_debug_pid.surfaceflinger=30310\n", append=True)
    f.executable("bin/dumpsys", """#!/bin/sh
case "$1" in
    --pid) cat "$ONEIOS_TEST_ROOT/pids/system_server" ;;
    input) printf 'Input Reader State\nsec_touchscreen\nInput Dispatcher State\n' ;;
    *) exit 1 ;;
esac
""")
    f.executable("bin/input", '#!/bin/sh\n[ "$*" = "keyevent KEYCODE_SHIFT_LEFT" ]\n')
    f.write(f"{SESSION}/control/watchdog.generation", "fixture-framework\n")


def framework_stop_needs_all_recovery_helpers(f):
    framework_setup(f)
    f.write("props", "init.svc.zygote_next=running\n", append=True)
    f.write("pids/zygote_next", "30323\n")
    f.proc(30323, "zygote_next")
    f.write("sys/power/wake_lock", "oneios_session\n")
    for pid, name in ((801, "framework.guard"), (802, "framework.watcher"),
                      (803, "keys/reader.803"), (804, "keys/reader.804"),
                      (805, "keys/reader.805")):
        f.proc(pid, "recovery-helper")
        f.write(f"{SESSION}/control/{name}", f"{pid} 800\n")
    f.write(f"{SESSION}/control/keys/pids", "803\n804\n805\n")
    f.write(f"{SESSION}/control/keys/reader.805", "805 799\n")
    f.check("unverified reader refuses the stop", 1, f.run("switch", "--framework-test-stop")[0])
    f.check("no service stopped before recovery is armed", [], f.log("setprop"))
    f.write(f"{SESSION}/control/keys/reader.805", "805 800\n")
    f.check("armed stop completed", 0, f.run("switch", "--framework-test-stop")[0])
    f.check("only framework services stopped", ["ctl.stop zygote", "ctl.stop zygote_secondary",
                                                "ctl.stop zygote_next"], f.log("setprop"))
    f.check("system_server ended", "", f.read(f.root / "pids/system_server"))


def framework_smoke(f):
    framework_setup(f)
    f.write(f"{SESSION}/control/framework.mode", "smoke\n")
    f.write(f"{SESSION}/control/framework.cutoff", "110\n")
    f.write(f"{SESSION}/control/framework.deadline", "110\n")
    f.write("proc/uptime", "110.00 0.00\n")
    f.write(f"{SESSION}/control/state", "running\n")


def framework_deadline_after_watcher_loss(f):
    framework_smoke(f)
    f.check("deadline invokes in-place return without a watcher", 0,
            f.run("switch", "--framework-deadline", "fixture-framework")[0])
    commands = f.log("setprop")
    f.check("zygote recovered", True, "ctl.start zygote" in commands)
    f.check("display and vendor services never restarted", [],
            [command for command in commands if command.startswith(("ctl.restart", "ctl.stop"))])
    f.check("no guest start", False, (f.control / "framework.guest").exists())
    f.check("in-place return completed", True, f.outcome().startswith("inplace "))
    f.check("watcher loss does not qualify a smoke test", "", f.read(f.stage / "smoke.accepted"))


def framework_timed_smoke(f):
    framework_smoke(f)
    f.proc(802, "mock-recovery-watcher")
    f.write(f"{SESSION}/control/framework.watcher", "802 800\n")
    f.check("elapsed smoke returned", 0, f.run("switch", "--framework-deadline", "fixture-framework")[0])
    f.check("completed smoke gives a boot-scoped result", "phase3-boot", f.read(f.stage / "smoke.accepted"))


def framework_reboot_key_requests_oneui_restart(f):
    framework_smoke(f)
    f.write(f"{SESSION}/control/framework.return", "reboot\n")
    f.write(f"{SESSION}/session/return.request",
            "keys: Volume Up + Volume Down held 3 s\n")
    rc, _ = f.run("return", "watcher", "fixture-framework")
    f.check("reboot-only key return signals init", True,
            "sys.powerctl reboot,oneios-sm8850-reboot-return" in f.log("setprop"))
    f.check("hardware chord is recorded before reboot", True,
            f.outcome().startswith("reboot-key "))
    f.check("no zygote restart attempted", False,
            "ctl.start zygote" in f.log("setprop"))
    f.check("reboot branch does not require native watchdog handback", False,
            (f.control / "watchdog.handback").exists())
    f.check("reboot-only branch terminates without claiming in-place", 1, rc)


def framework_reboot_deadline_cannot_claim_key_success(f):
    framework_smoke(f)
    f.write(f"{SESSION}/control/framework.return", "reboot\n")
    f.write(f"{SESSION}/session/return.request", "deadline reached\n")
    rc, _ = f.run("return", "framework-deadline", "fixture-framework")
    f.check("deadline requests reboot", True,
            "sys.powerctl reboot,oneios-sm8850-reboot-return" in f.log("setprop"))
    f.check("deadline is not a hardware-key PASS", True,
            f.outcome().startswith("reboot-deadline-or-manual "))
    f.check("no in-place return claimed", False, f.outcome().startswith("inplace "))
    f.check("deadline return exits by reboot fallback", 1, rc)


def framework_stale_deadline(f):
    f.env["ONEIOS_TEST_FRAMEWORK"] = "1"
    f.write(f"{SESSION}/control/watchdog.generation", "fixture-next\n")
    f.write(f"{SESSION}/control/framework.cutoff", "1\n")
    f.check("a stale deadline exits", 0,
            f.run("switch", "--framework-deadline", "fixture-old")[0])
    f.check("a stale deadline cannot operate init", [], f.log("setprop"))


def framework_manual_return_restores_map_count(f):
    framework_setup(f)
    f.write(f"{SESSION}/control/framework.mode", "run\n")
    f.write(f"{SESSION}/control/base/max_map_count", "65530 1048576\n")
    f.write("proc/sys/vm/max_map_count", "1048576\n")
    f.check("manual return completed", 0, f.run("return", "framework-deadline", "fixture-framework")[0])
    f.check("original VMA limit restored", "65530", f.read(f.root / "proc/sys/vm/max_map_count"))
    f.check("manual return does not certify a full-duration run", "",
            f.read(f.control / "framework.result"))


def framework_changed_service_uses_failsafe(f):
    framework_setup(f)
    f.write("props", f"init.svc_debug_pid.{COMPOSER}=30543\n", append=True)
    f.check("unexpected vendor service replacement failed recovery", 1,
            f.run("return", "framework-deadline", "fixture-framework")[0])
    f.check("guarded reboot requested", True, "sys.powerctl reboot,oneios-inplace-failsafe" in f.log("setprop"))
    f.check("failure identifies protected service", True,
            f"protected service {COMPOSER}" in f.outcome())


WD_ATTR = "sys/class/watchdog/watchdog0"


def native_handback_fixture(f, mode):
    framework_setup(f)
    f.write(f"{SESSION}/control/watchdog.target", "watchdog0 f2:0\n")
    f.write(f"{SESSION}/control/watchdog.plan", f"{mode} 120 20 fixture-supervisor\n")
    f.write(f"{SESSION}/control/watchdog.owner", "30321\n")
    f.write(f"{SESSION}/control/feeder.arm", "fixture-framework 100\n")
    f.write(f"{SESSION}/control/feeder.heartbeat", "fixture-framework 4500 800 100\n")
    f.write(f"{SESSION}/control/feeder.pid", "4500\n")
    f.write(f"{SESSION}/control/feeder.ready", "4500\n")
    f.proc(4500, "oneios-watchdog")
    f.write(f"{WD_ATTR}/nowayout", f"{mode}\n")
    f.write(f"{WD_ATTR}/timeleft", "110\n")
    f.write("behave/native-watchdog-probe", "")


def native_release(f, mode):
    f.write(f"{WD_ATTR}/state", "active\n" if mode else "inactive\n")
    f.write(f"{SESSION}/control/watchdog.phase", "fixture-framework RETURN_PENDING\n")
    f.write(f"{SESSION}/control/feeder.released", f"fixture-framework 4500 800 {mode} 100\n")
    shutil.rmtree(f.root / "proc/4500")


def native_framework_birth(f):
    pid = wait_for("new system_server PID", lambda: f.read(f.root / "pids/system_server"))
    f.write(f"proc/{pid}/stat", f"{pid} (system_server) S " + "0 " * 18 + "801\n")


def native_handback_armed_without_transport(f):
    framework_smoke(f)
    native_handback_fixture(f, 1)
    f.write("proc/uptime", "100.00 0.00\n")
    f.write(f"{SESSION}/control/framework.deadline", "100\n")
    f.proc(802, "mock-recovery-watcher")
    f.write(f"{SESSION}/control/framework.watcher", "802 800\n")
    process, _ = f.start("switch", "--framework-deadline", "fixture-framework")
    wait_for("independent recovery requests release", lambda: (f.control / "feeder.off").exists())
    f.check("zygote cannot start while supervisor still owns the endpoint", False,
            "ctl.start zygote" in f.log("setprop"))
    native_release(f, 1)
    native_framework_birth(f)
    wait_for("new framework owner sampled", lambda: f.read(f.clock / "timeleft-reads").count("read") >= 2)
    f.write(f"{WD_ATTR}/timeleft", "119\n")
    f.check("returns with no ADB process", 0, process.wait(15))
    f.check("first framework ping sampled", True, "FRAMEWORK_REACQUIRED:" in f.return_log())
    f.check("close reached the log before zygote start", True,
            0 <= f.return_log().find("native descriptor closed") < f.return_log().find("zygote started"))
    f.check("independent timer smoke verified", "phase3-boot", f.read(f.stage / "smoke.accepted"))


def native_handback_disarmed_after_delayed_framework(f):
    native_handback_fixture(f, 0)
    process, _ = f.start("return", "framework-deadline", "fixture-framework")
    wait_for("release requested", lambda: (f.control / "feeder.off").exists())
    native_release(f, 0)
    f.write("proc/uptime", "110.00 0.00\n")
    native_framework_birth(f)
    wait_for("initial observation of new framework owner", lambda: (f.clock / "timeleft-reads").exists())
    f.check("ownership alone does not certify handback", False, "FRAMEWORK_REACQUIRED" in f.return_log())
    f.write(f"{WD_ATTR}/timeleft", "118\n")
    f.check("delayed observation completes before the deadline", 0, process.wait(15))
    f.check("disarmed state verified before restart", True, "nowayout=0 state=inactive" in f.return_log())
    f.check("result is in-place", True, f.outcome().startswith("inplace "))


def native_handback_missing_release_failsafe(f):
    native_handback_fixture(f, 1)
    process, _ = f.start("return", "framework-deadline", "fixture-framework")
    wait_for("release requested", lambda: (f.control / "feeder.off").exists())
    f.write("proc/uptime", "120.00 0.00\n")
    f.check("timed out handback exits with failure", 1, process.wait(15))
    f.check("zygote not started without a release receipt", False, "ctl.start zygote" in f.log("setprop"))
    f.check("guarded reboot", True, "sys.powerctl reboot,oneios-inplace-failsafe" in f.log("setprop"))
    f.check("timeout logged", True, "watchdog handback time" in f.outcome())


def native_handback_stuck_framework_guard(f):
    native_handback_fixture(f, 1)
    f.write("behave/hang_ctl.start_zygote", "")
    f.start("return", "framework-deadline", "fixture-framework")
    wait_for("release requested", lambda: (f.control / "feeder.off").exists())
    native_release(f, 1)
    wait_for("framework restart hangs", lambda: "ctl.start zygote" in f.log("setprop"))
    f.write("proc/uptime", "120.00 0.00\n")
    wait_for("independent guard reboot", lambda: "sys.powerctl reboot,oneios-inplace-failsafe" in f.log("setprop"))
    f.check("guard diagnosed the stuck framework", True, "independent guard saw watchdog handback timeout" in f.outcome())
    f.check("no reacquisition certificate", "fixture-framework RETURN_PENDING", f.read(f.control / "watchdog.phase"))


def native_handback_missing_guard_refuses_release(f):
    native_handback_fixture(f, 0)
    f.write("behave/native-guard-unavailable", "")
    f.check("return failed without a guard", 1, f.run("return", "framework-deadline", "fixture-framework")[0])
    f.check("supervisor was never asked to disarm", False, (f.control / "feeder.off").exists())
    f.check("guard failure logged", True, "independent handback guard was not armed" in f.outcome())
    f.check("zygote was not started", False, "ctl.start zygote" in f.log("setprop"))


def native_crashed_supervisor_uses_failsafe(f):
    native_handback_fixture(f, 1)
    shutil.rmtree(f.root / "proc/4500")
    f.check("return detected the dead supervisor", 1, f.run("return", "framework-deadline", "fixture-framework")[0])
    f.check("zygote was not started", False, "ctl.start zygote" in f.log("setprop"))
    f.check("failure recorded", True, f.outcome().startswith("failsafe "))
    f.check("guarded reboot requested", True, "sys.powerctl reboot,oneios-inplace-failsafe" in f.log("setprop"))


CASES = (
    event_chord_and_watcher, single_key_without_accessory, brief_bounce, premature_release,
    polling_after_watcher_death, watcher_without_return_script, lost_feeder, stale_lock_and_watch_race,
    pid_fallback_usb_and_baseline, early_return_with_stale_stop_lock,
    gate_a_failure, gate_b_failure, gate_c_failure,
    watchdog_s26_refused, watchdog_exclusive_open_busy, watchdog_ping_fails_after_first_success,
    watchdog_stuck_feeder, watchdog_handoff_order, watchdog_framework_never_reacquires,
    watchdog_invalid_heartbeat, watchdog_delayed_first_ping, watchdog_concurrent_recovery,
    watchdog_blocked_second_ping, watchdog_guard_supervises_a_return,
)
FRAMEWORK_CASES = (framework_stop_needs_all_recovery_helpers, framework_deadline_after_watcher_loss,
                   framework_timed_smoke, framework_reboot_key_requests_oneui_restart,
                   framework_reboot_deadline_cannot_claim_key_success,
                   framework_stale_deadline, framework_manual_return_restores_map_count,
                   framework_changed_service_uses_failsafe, native_handback_armed_without_transport,
                   native_handback_disarmed_after_delayed_framework, native_handback_missing_release_failsafe,
                   native_handback_stuck_framework_guard, native_handback_missing_guard_refuses_release,
                   native_crashed_supervisor_uses_failsafe)


def worker(shell, definition):
    if Path.cwd() != Path("/phone") or not Path("/phone/source").is_dir() or os.geteuid() == 0:
        raise RuntimeError("Recovery cases require the unprivileged /phone sandbox")
    with tempfile.TemporaryDirectory(prefix="fixture-", dir="/phone") as temp:
        fixture = Fixture(Path(temp), shell, early=definition in
                          (early_return_with_stale_stop_lock, framework_stop_needs_all_recovery_helpers))
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
    parser.add_argument("--working-tree", action="store_true", help="Test the local OneOS changes and record their hashes")
    parser.add_argument("--case", action="append", choices=[case.__name__ for case in CASES + FRAMEWORK_CASES],
                        help="Run selected cases in both shells")
    args = parser.parse_args()
    if os.geteuid() == 0 or not shutil.which("bwrap") or not args.mksh or not os.access(args.mksh, os.X_OK):
        parser.error("requires non-root CachyOS with bwrap and an executable mksh (use --mksh)")
    pin = git("ls-tree", "HEAD", "app").decode().split()[2]
    app_head = git("-C", "app", "rev-parse", "HEAD").decode().strip()
    if git("diff", "--cached", "--name-only", "--", "app"):
        parser.error("the app index must match the parent gitlink")
    if not args.working_tree:
        git("-C", "app", "cat-file", "-e", f"{pin}^{{commit}}")
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
    selected = [case for case in CASES + (FRAMEWORK_CASES if args.working_tree else ())
                if args.case is None or case.__name__ in args.case]
    if not selected:
        parser.error("experimental fixture cases require --working-tree")
    with args.output.open("x") as report, tempfile.TemporaryDirectory(prefix="oneios-recovery-") as temp:
        path = Path(temp)
        (path / "source").mkdir()
        hashes = {}
        for label, name in PINNED_FILES.items():
            payload = ((Path(__file__).resolve().parents[2] / "app" / name).read_bytes()
                       if args.working_tree else git("-C", "app", "show", f"{pin}:{name}"))
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
            "oneos_worktree_head": app_head,
            "oneos_script_source": "working tree" if args.working_tree else "gitlink",
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
                {"check": "boot iOS on SM8850", "status": "BLOCKED",
                 "expected": "Authorized switch with a verified image set", "actual": "Host boot evidence only; device switching disabled"},
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
        fn = next(definition for definition in CASES + FRAMEWORK_CASES if definition.__name__ == sys.argv[3])
        print(json.dumps(worker(sys.argv[2], fn)))
    else:
        raise SystemExit(main())
