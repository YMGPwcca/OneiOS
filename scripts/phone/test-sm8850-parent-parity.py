#!/usr/bin/env python3
"""Offline source-level parity invariants for the direct-parent SM8850 port.

No ADB, root, device access or guest execution. The full integrated runner
combines this check with host tests and a separately validated GPU3D build.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

IOS = Path(__file__).resolve().parents[2]
OS = Path(os.environ.get("ONEOS_REPO", str(IOS / "app")))


def content(root: Path, rel: str) -> str:
    path = root / rel
    if not path.is_file():
        raise AssertionError(f"MISSING_SOURCE {path}")
    return path.read_text()


def require(root: Path, rel: str, *needles: str) -> None:
    body = content(root, rel)
    for needle in needles:
        if needle not in body:
            raise AssertionError(f"MISSING_INVARIANT {root.name}/{rel}: {needle}")


def check() -> None:
    require(IOS, "runtime/bridges/cpu/topology.c",
            "c->implementer != 0x51", "bool lent[BR_MAX_CPUS]",
            "br_cpu_plan_make(", "br_cpu_pin_mask(")
    require(IOS, "runtime/bridges/include/bridges/bridges.h",
            "unsigned implementer;", "br_haptic_impacts_available")
    require(IOS, "runtime/bridges/tests/test_bridges.c",
            "test_sm8850_cpu", "t.ncpu == 8 && t.n_e == 0 && t.n_p == 8",
            "plan.n_e == 2 && plan.n_p == 6")
    require(IOS, "runtime/xnuhost/src/main.c",
            "br_cpu_plan_make(&host, 8, true, &parent_plan)",
            "config.cpu_affinity_bench && bench_affinity_init()")
    require(IOS, "runtime/xnuhost/src/gpu3d_kgsl.c",
            '#include "virgl_fence.h"', "virgl_fence_table_init()")
    require(IOS, "runtime/xnuhost/drm2kgsl/patches/0007-a830-waittimestamp-fences.patch",
            "NCTX_NO_WAITTS", "+   return true;")
    metal = (
        "0101-large-indexed-constants-to-blob.patch",
        "0102-blob-constant-gep-pointers.patch",
        "0103-block-bytes-per-process.patch",
    )
    for name in metal:
        require(IOS, "userland/metal/patches/metal2vulkan/" + name,
                "diff --git")
    require(IOS, "userland/metal/build.sh",
            '9$(basename "$p")', 'count" -eq 3',
            "staged $count direct-parent metal2vulkan patches")
    require(IOS, "scripts/ci-local.sh",
            "scripts/setup/get-references.sh virglrenderer",
            "this build has no drm2kgsl", "runtime/package.sh")
    switch = content(OS, "switcher/assets/oneios_switch.sh")
    stage = switch.index('echo "ONEIOS_TAKEOVER_CPU=8')
    end = switch.index('die_inner "could not exec the GPU-3D benchmark runtime"')
    bench = switch[stage:end]
    for value in (
        "--cpus 8 --ram 4G",
        "--set ram-giveback=0 --set ram-prefault=1 --set ram-lock=1",
        "--set bridges=0 --set wifi=off",
        "--set cpu-pin=1 --set cpu-affinity-bench=1",
        "--set gpu-level=deadline --set gpu-priority=1 --set setway-skip=1",
        "--set spin-host=0 --set spin-task=0",
        "--gpu auto --display shm",
    ):
        if value not in bench:
            raise AssertionError(f"MISSING_BENCH_INVARIANT {value}")
    for prohibited in ("--set bridges=1", "--set ram-giveback=1",
                       "--set gpu-level=hold", "--set spin-host=1000"):
        if prohibited in bench:
            raise AssertionError(f"UNSAFE_BENCH_OPTION {prohibited}")
    for needle in (
        "P0_FULL_600S_TAKEOVER=BLOCKED_UNQUALIFIED_THERMAL_GUARD",
        "framework_thermal_guard_healthy()",
        "P0_SHORT_PROBE_THERMAL=ARMED_ROOT_SENSOR_GUARD_NOT_PRODUCTION_CERTIFIED",
    ):
        if needle not in switch:
            raise AssertionError(f"MISSING_RECOVERY_INVARIANT {needle}")
    require(OS, "switcher/assets/oneios_sm8850_thermal_takeover_guard.sh",
            '"$CPU_MAX" -lt 55000',
            "P0_THERMAL_GUARD=FAIL_CLOSED",
            "P0_THERMAL_SAMPLE=OK",
            "P0_XNUHOST_LOAD=READ_ONLY",
            "case $((seq % 5)) in")
    require(OS, "tests/run_sm8850_thermal_local.sh", "EXPECTED_TESTS=179")
    # The first complete-run failure was the orchestration itself: an invalid
    # package version and a truncated AdrenoPM4 git SHA. Check both before
    # spending CPU on CI; do not replace those checks with a loose prefix.
    runner = content(IOS, "scripts/sm8850-parent-integration-all.sh")
    v = re.search(r'^VERSION="([^"]+)"$', runner, re.MULTILINE)
    if not v or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z][0-9A-Za-z.]*)?", v.group(1)):
        raise AssertionError("INVALID_RUNTIME_PACKAGE_VERSION")
    required_pin = "282606b528b2595bc4274ea7490b62b323f35a5f"
    if runner.count(required_pin) < 2:
        raise AssertionError("ADRENOPM4_PIN_TRUNCATED_IN_RUNNER")
    if required_pin not in content(IOS, "scripts/setup/get-references.sh"):
        raise AssertionError("ADRENOPM4_PIN_DISAGREES_WITH_REFERENCE_TABLE")
    for setting in ("--continue --max-workers=3", "ONEOS_GRADLE_FAILURES.txt",
                    "gradle-test-results", "gradle-html-reports",
                    "PARENT_DRIFT", "DOCUMENTATION_ONLY_NO_EXECUTABLE_CODE_DRIFT",
                    "SM8850_PARENT_INTEGRATION=PASS_OFFLINE_NO_PHONE"):
        if setting not in runner:
            raise AssertionError(f"INTEGRATION_MISSING {setting}")
    forbidden = ("adb shell", "fastboot flash", "sys.powerctl", "rearm-data")
    for value in forbidden:
        if value in runner:
            raise AssertionError(f"INTEGRATION_PHONE_ACTION {value}")
    syntax = subprocess.run(["bash", "-n", str(IOS / "scripts/sm8850-parent-integration-all.sh")],
                            capture_output=True, text=True)
    if syntax.returncode:
        raise AssertionError(f"INTEGRATION_SHELL_SYNTAX {syntax.stderr[:1000]}")
    print("SM8850_PARENT_PARITY_STATIC=PASS_SOURCE_ONLY")
    print("SM8850_PHYSICAL_THERMAL_RECOVERY=NOT_CERTIFIED")


if __name__ == "__main__":
    check()
