#!/usr/bin/env python3
"""Exercise the REAL pinned OneOS reboot-smoke watchdog loop with fake files.

Both production and test invoke the same function body from oneios_switch.sh.
No phone, root permission, Android watchdog device, or USB access is used.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SWITCH = ROOT / "app/switcher/assets/oneios_switch.sh"
ONEOS_ANDROID = ROOT / "app/switcher/assets/oneos_switch.sh"
FUNC_HEAD = "watchdog_pings() {\n"
FUNC_TAIL = "\n}\nwatchdog_feed() {"

STUB = r"""#!/bin/sh
root=$ONEIOS_FAKE_ROOT
n=$(cat "$root/count")
n=$((n + 1))
echo "$n" > "$root/count"
echo "$n" >> "$root/attempts"
echo "$((100 + n))" > "$root/tick"
case "$ONEIOS_STUB_MODE:$n" in
    transient:1|transient:2|permanent:*|second-fail:2)
        echo "Device or resource busy" >&2
        exit 1 ;;
esac
if [ "$ONEIOS_STUB_MODE" = transient ]; then
    touch "$root/ctl/feeder.off"
fi
exit 0
"""

HARNESS = r"""#!/bin/sh
T=$ONEIOS_FAKE_ROOT
CTL=$T/ctl
WD_GEN=fixture-generation
FRAMEWORK_REBOOT=1
WD_FIRST=10
WD_MAX_AGE=5
wd_armed=100
wd_name=legacy
wd_saved=a:82
wd_birth=800
L=$T/legacy-feeder.log
watchdog_id() { printf 'a:82\n'; }
watchdog_generation() { printf '%s\n' "$WD_GEN"; }
watchdog_now() { cat "$T/tick"; }
watchdog_failed() { printf '%s\n' "$*" > "$T/failure"; }
sleep() { /bin/sleep 0.005; }
__FUNCTION__
watchdog_pings
"""


class OneOSLegacyFeederTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        content = SWITCH.read_text()
        cls.content = content
        if content.count(FUNC_HEAD) != 1 or content.count(FUNC_TAIL) != 1:
            raise AssertionError("pinned OneOS watchdog loop anchor changed")
        cls.source_function = FUNC_HEAD + content.split(FUNC_HEAD, 1)[1].split(FUNC_TAIL, 1)[0] + "\n}"
        cls.shells = [shutil.which("bash")]
        mksh = os.environ.get("ONEOS_TEST_MKSH") or shutil.which("mksh")
        if mksh:
            cls.shells.append(mksh)
        cls.shells = [path for path in cls.shells if path]

    def simulate(self, mode, shell):
        with tempfile.TemporaryDirectory(prefix="oneos-legacy-v-") as tmp:
            root = Path(tmp)
            (root / "bin").mkdir()
            (root / "ctl").mkdir()
            (root / "count").write_text("0\n")
            (root / "tick").write_text("100\n")
            (root / "ctl" / "watchdog.generation").write_text("fixture-generation\n")
            tool = root / "bin" / "watchdog-io"
            tool.write_text(STUB)
            tool.chmod(0o700)
            script = root / "harness.sh"
            script.write_text(HARNESS.replace("__FUNCTION__", self.source_function))
            env = os.environ.copy()
            env.update(ONEIOS_FAKE_ROOT=str(root), ONEIOS_STUB_MODE=mode)
            result = subprocess.run(
                [shell, str(script)], capture_output=True, text=True,
                env=env, timeout=10,
            )
            return (
                result,
                (root / "attempts").read_text().splitlines()
                if (root / "attempts").exists() else [],
                (root / "ctl" / "feeder.ready").exists(),
                (root / "ctl" / "feeder.heartbeat").read_text()
                if (root / "ctl" / "feeder.heartbeat").exists() else "",
                (root / "failure").read_text()
                if (root / "failure").exists() else "",
                (root / "legacy-feeder.log").read_text()
                if (root / "legacy-feeder.log").exists() else "",
            )

    def test_uses_original_oneos_magic_close_before_feeder(self):
        oneos = ONEOS_ANDROID.read_text()
        self.assertIn("SOFTDOG_V=0", oneos)
        self.assertIn("if e=$(printf V 2>&1 > /dev/watchdog)", oneos)
        self.assertIn("if e=$(printf V 2>&1 > /dev/watchdog)", (ROOT / "app/switcher/assets/guest_prepare.sh").read_text())
        self.assertIn("OneOS legacy /dev/watchdog magic close", self.content)
        after_stop = self.content.index("if ! stop_android_framework; then")
        magic = self.content.index("OneOS legacy /dev/watchdog magic close", after_stop)
        feeder = self.content.index("watchdog_started() {", after_stop)
        self.assertLess(after_stop, magic)
        self.assertLess(magic, feeder)
        self.assertIn('if [ "$FRAMEWORK_REBOOT" = 1 ]; then', self.content[after_stop:feeder])
        self.assertIn("WD_FIRST=10", self.content)
        for child in ("--feed:*", "--watch:*", "--framework-deadline:*", "--keys:*",
                      "--keys-poll:*", "--watchdog-health:*"):
            with self.subTest(child=child):
                self.assertIn(child, self.content)

    def test_two_initial_ebusy_events_are_not_counted_as_keepalives(self):
        for shell in self.shells:
            with self.subTest(shell=shell):
                result, attempts, ready, heartbeat, failed, log = self.simulate("transient", shell)
                self.assertEqual(0, result.returncode, (result.stdout, result.stderr))
                self.assertEqual(["1", "2", "3"], attempts)
                self.assertTrue(ready)
                self.assertIn("fixture-generation", heartbeat)
                self.assertTrue(heartbeat.strip().endswith("103"))
                self.assertEqual("", failed)
                self.assertEqual(2, log.count("V refused"))

    def test_permanent_ebusy_has_bounded_failure_and_no_false_heartbeat(self):
        for shell in self.shells:
            with self.subTest(shell=shell):
                result, attempts, ready, heartbeat, failed, log = self.simulate("permanent", shell)
                self.assertEqual(1, result.returncode, (result.stdout, result.stderr))
                self.assertEqual(10, len(attempts))
                self.assertFalse(ready)
                self.assertEqual("", heartbeat)
                self.assertIn("never succeeded within bounded handoff", failed)
                self.assertIn("V refused", log)

    def test_error_after_first_real_v_fails_without_new_heartbeat(self):
        for shell in self.shells:
            with self.subTest(shell=shell):
                result, attempts, ready, heartbeat, failed, log = self.simulate("second-fail", shell)
                self.assertEqual(1, result.returncode, (result.stdout, result.stderr))
                self.assertEqual(["1", "2"], attempts)
                self.assertTrue(ready)
                self.assertTrue(heartbeat.strip().endswith("101"))
                self.assertEqual("", failed)


if __name__ == "__main__":
    unittest.main()
