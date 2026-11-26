#!/usr/bin/env python3
"""Collect only the exact stock PerfLock ELFs for private static analysis.

No vendor API call, sysfs write, device file creation, service change,
or guest launch. Archive only on the host; never commit vendor ELFs.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import zipfile

FILES = (
    "/vendor/lib64/libqti-perfd-client.so",
    "/vendor/lib64/libqti-perfd.so",
    "/vendor/lib64/libperfioctl.so",
    "/vendor/lib64/libperfconfig.so",
    "/vendor/lib64/vendor.qti.hardware.perf2-V1-ndk.so",
    "/vendor/bin/hw/vendor.qti.hardware.perf2-hal-service",
    "/system_ext/lib64/libqti-perfd-client_system.so",
)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adb", default=str(Path.home() / "Android/Sdk/platform-tools/adb"))
    ap.add_argument("--serial", required=True)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    if args.output.exists():
        ap.error("output already exists")
    adb = [args.adb, "-s", args.serial]

    def run(parts):
        return subprocess.run(adb + parts, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30, check=False)

    def read(cmd, root=False, binary=False):
        cmd = "su -c " + shlex.quote(cmd) if root else cmd
        p = run((["exec-out", cmd] if binary else ["shell", "-T", cmd]))
        if p.returncode:
            raise RuntimeError("read failed: " + cmd + ": " +
                               p.stderr.decode(errors="replace").strip())
        return p.stdout if binary else p.stdout.decode(errors="replace").strip()

    if run(["get-state"]).stdout.strip() != b"device":
        raise RuntimeError("ADB device not available")
    model = read("getprop ro.product.model")
    firmware = read("getprop ro.build.PDA")
    soc = read("cat /sys/devices/soc0/soc_id")
    if (model, firmware, soc) != ("SM-S948B", "S948BXXS4BZIG", "660"):
        raise RuntimeError("unexpected firmware or SoC")
    if read("getprop sys.boot_completed") != "1" or read("id -u", root=True) != "0":
        raise RuntimeError("stock boot or root read access missing")
    if not read("pidof system_server", root=True):
        raise RuntimeError("system_server missing")
    active = run(["shell", "-T", "su -c 'pidof xnuhost'"])
    if active.returncode != 1 or active.stdout.strip():
        raise RuntimeError("xnuhost absent not verified")

    manifest = {"model": model, "firmware": firmware, "soc_id": soc,
                "files": [], "purpose": "private static analysis; not provider qualification"}
    blobs = []
    for remote in FILES:
        q = shlex.quote(remote)
        size = int(read("stat -Lc %s " + q, root=True))
        if not 0 < size <= 16 * 1024 * 1024:
            raise RuntimeError("unexpected file size: " + remote)
        data = read("cat " + q, root=True, binary=True)
        # ELF64, little endian, AArch64 (e_machine = 183).
        if (len(data) != size or len(data) < 64 or
                data[:6] != b"\x7fELF\x02\x01" or data[18:20] != b"\xb7\x00"):
            raise RuntimeError("unexpected ELF identity: " + remote)
        name = str(PurePosixPath(remote).relative_to("/"))
        digest = hashlib.sha256(data).hexdigest()
        manifest["files"].append({"path": remote, "archive_path": name,
                                  "bytes": size, "sha256": digest})
        blobs.append((name, data))
        print(f"READ_OK {remote} bytes={size} sha256={digest}", flush=True)

    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in blobs:
            z.writestr(name, data)
        z.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
    print("STATIC_EVIDENCE=COLLECTED")
    print("FREQUENCY_PROVIDER=NOT_QUALIFIED")
    print("DEVICE_WRITES=NONE")
    print("EVIDENCE=" + str(args.output.resolve()))


if __name__ == "__main__":
    main()
