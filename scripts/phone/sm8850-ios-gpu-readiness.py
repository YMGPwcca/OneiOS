#!/usr/bin/env python3
"""Read-only SM8850 iOS GPU bench inventory: never boot, copy or modify guest Data."""

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BENCH = "/data/local/tmp/oneios-m3q-ios27-bench"
SOURCE_FILES = (
    "data/data.img", "data/unique-chip-id", "image/kernel.kc",
    "image/kernel.kc.gpuaddon", "image/manifest.json", "image/os.img",
    "image/systemos.img", "image/app.img", "bench/xnuhost-gui-bench",
)
DATA_BYTES = 8 * 1024**3
CLONE_MARGIN_KIB = 2 * 1024**2

# Fixed paths, read-only operations, no shell interpolation from arguments.
DEVICE_ASSET_AUDIT = r'''set -eu
B=/data/local/tmp/oneios-m3q-ios27-bench
for rel in data/data.img data/unique-chip-id image/kernel.kc image/kernel.kc.gpuaddon image/manifest.json image/os.img image/systemos.img image/app.img bench/xnuhost-gui-bench; do
    p="$B/$rel"
    if [ -f "$p" ] && [ ! -L "$p" ]; then
        printf 'FILE|%s|%s\n' "$rel" "$(stat -c '%s:%h:%u:%a:%d:%i' "$p")"
    else
        printf 'FILE|%s|MISSING\n' "$rel"
    fi
done
for rel in image/xnuhost.conf image/overlay/userland/xnuhost.conf; do
    p="$B/$rel"
    if [ -f "$p" ] && [ ! -L "$p" ]; then
        printf 'CONFIG|%s|BEGIN\n' "$rel"
        sed -n '1,120p' "$p" | sed 's/^/LINE|/'
        printf 'CONFIG|%s|END\n' "$rel"
    else
        printf 'CONFIG|%s|ABSENT\n' "$rel"
    fi
done
for rel in image/kernel.kc.gpuaddon bench/xnuhost-gui-bench; do
    p="$B/$rel"
    if [ -f "$p" ] && [ ! -L "$p" ]; then
        printf 'SHA256|%s|%s\n' "$rel" "$(sha256sum "$p" | cut -d ' ' -f 1)"
    fi
done
'''


def load_harness():
    path = HERE / "sm8850-gpu-acceptance.py"
    spec = importlib.util.spec_from_file_location("oneios_sm8850_gpu_acceptance", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("SM8850 GPU harness is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_asset_audit(content):
    """Strictly parse tagged inventory, rejecting duplicate or malformed asset records."""
    files = {}
    digests = {}
    configs = {}
    current_config = None
    for line in content.splitlines():
        if line.startswith("FILE|"):
            _, name, metadata = line.split("|", 2)
            if name not in SOURCE_FILES or name in files:
                raise ValueError("unexpected or duplicate asset: " + name)
            if metadata != "MISSING" and not re.fullmatch(r"\d+:\d+:\d+:[0-7]+:\d+:\d+", metadata):
                raise ValueError("invalid asset stat: " + name)
            files[name] = metadata
        elif line.startswith("SHA256|"):
            _, name, digest = line.split("|", 2)
            if name not in ("image/kernel.kc.gpuaddon", "bench/xnuhost-gui-bench") or name in digests:
                raise ValueError("unexpected or duplicate digest")
            if not re.fullmatch("[a-f0-9]{64}", digest):
                raise ValueError("invalid digest")
            digests[name] = digest
        elif line.startswith("CONFIG|"):
            _, name, event = line.split("|", 2)
            if name not in ("image/xnuhost.conf", "image/overlay/userland/xnuhost.conf"):
                raise ValueError("unexpected config")
            if event == "BEGIN" and current_config is None and name not in configs:
                configs[name] = []
                current_config = name
            elif event == "END" and current_config == name:
                current_config = None
            elif event == "ABSENT" and current_config is None and name not in configs:
                configs[name] = None
            else:
                raise ValueError("malformed config boundary")
        elif line.startswith("LINE|") and current_config is not None:
            configs[current_config].append(line[5:])
        else:
            raise ValueError("unexpected asset audit output")
    if current_config is not None or set(files) != set(SOURCE_FILES):
        raise ValueError("incomplete asset audit")
    if set(configs) != {"image/xnuhost.conf", "image/overlay/userland/xnuhost.conf"}:
        raise ValueError("incomplete config audit")
    return {"files": files, "sha256": digests, "configs": configs}


def evaluate_inventory(preflight, inventory):
    """A source tree can be complete without being safe to launch as a writable guest."""
    files = inventory["files"]
    def parts(path):
        value = files[path]
        return None if value == "MISSING" else [int(x, 10 if i != 3 else 8) for i, x in enumerate(value.split(":"))]

    source_complete = all(parts(name) is not None and parts(name)[0] > 0 for name in SOURCE_FILES)
    data = parts("data/data.img")
    chip = parts("data/unique-chip-id")
    pair_sizes = bool(data and chip and data[0] == DATA_BYTES and chip[0] == 8)
    distinct_inodes = bool(data and chip and data[1] == 1 and chip[1] == 1 and (data[4], data[5]) != (chip[4], chip[5]))
    free_raw = preflight.get("free_kib", "")
    free = int(free_raw) if free_raw.isdigit() else 0
    required = (30 * 1024**2 + 65536 + DATA_BYTES // 1024 + CLONE_MARGIN_KIB)
    return {
        "source_complete": source_complete,
        "data_pair_sizes": pair_sizes,
        "data_pair_single_link": distinct_inodes,
        "projected_clone_space": free >= required,
        "available_kib": free,
        "required_before_independent_copy_kib": required,
        "critical_note": "Original bench Data is never approved for writable guest execution.",
        "GUEST_RUN_READY": "BLOCKED",
        "why_blocked": (
            "An independent verified writable Data copy, matching updated xnuhost and instrumented GPU addon, "
            "effective disk configuration, bounded guest stop, and rollback checks still require approval."
        ),
    }


def local_artifacts():
    paths = (
        ROOT / "runtime/xnuhost/build/android/xnuhost",
        ROOT / "out/userland/NativeAdrenoMetal.gpuaddon",
        ROOT / "out/sm8850/gui-crash/local-validation/metal/NativeAdrenoMetal.gpuaddon",
    )
    output = {}
    for p in paths:
        name = str(p.relative_to(ROOT))
        output[name] = {"exists": p.is_file()}
        if p.is_file():
            output[name].update(size=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default=shutil.which("adb") or str(Path.home() / "Android/Sdk/platform-tools/adb"))
    parser.add_argument("--serial")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    out = args.output or ROOT / "out/sm8850/gpu-acceptance" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-ios-readiness.json")
    report = {"scope": "passive only; no guest boot, no Data copy and no device settings changed",
              "GUEST_RUN_READY": "BLOCKED", "IOS_VULKAN": "UNVERIFIED", "FRAMEWORK_TAKEOVER": "BLOCKED"}
    status = 0
    try:
        harness = load_harness()
        adb = harness.select_usb(args.adb, args.serial)
        report["usb_serial"] = adb[-1]
        base = harness.decode_kv(harness.root(adb, harness.DEVICE_AUDIT).stdout)
        checks, failures = harness.validate_preflight(base)
        report["device"] = {"values": base, "checks": checks, "failures": failures}
        if failures:
            raise harness.Blocked("device preflight: " + ", ".join(failures))
        inventory = parse_asset_audit(harness.root(adb, DEVICE_ASSET_AUDIT, seconds=120).stdout)
        report["inventory"] = inventory
        report["assessment"] = evaluate_inventory(base, inventory)
        report["local_artifacts"] = local_artifacts()
        if not all(report["assessment"][k] for k in
                   ("source_complete", "data_pair_sizes", "data_pair_single_link", "projected_clone_space")):
            status = 2
        print("SOURCE_ASSETS=" + ("PASS" if status == 0 else "BLOCKED"))
        print("GUEST_RUN_READY=BLOCKED (no verified isolated writable Data or qualified guest runner)")
        print("IOS_VULKAN=UNVERIFIED")
    except (OSError, ValueError, RuntimeError) as exc:
        status = 2
        report["error"] = str(exc)
        print("BLOCKED: " + str(exc), file=sys.stderr)
    finally:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("REPORT=" + str(out))
    return status


if __name__ == "__main__":
    sys.exit(main())
