#!/usr/bin/env python3
"""Read-only firmware inventory; never acquire a performance vote.

Run while stock One UI is running. Report candidate APIs and resource
mappings only, not provider qualification. Vendor ELF files are read into
a temporary directory on the host solely for static symbol inspection.
No code from those files is executed or uploaded.
"""
import argparse
import pathlib
import re
import shlex
import shutil
import subprocess
import tempfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adb", default=str(pathlib.Path.home() / "Android/Sdk/platform-tools/adb"))
    ap.add_argument("--serial", required=True)
    args = ap.parse_args()
    adb = [args.adb, "-s", args.serial]

    def run(argv, timeout=20):
        return subprocess.run(argv, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, check=False)

    def remote(command, root=True, binary=False):
        cmd = "su -c " + shlex.quote(command) if root else command
        # A single quoted command string; no stdin or device-side temp files.
        return run(adb + (["exec-out", cmd] if binary else ["shell", "-T", cmd]))

    def value(command, root=True):
        p = remote(command, root=root)
        if p.returncode:
            raise SystemExit("Read failed: " + command + ": " +
                             p.stderr.decode(errors="replace").strip())
        return p.stdout.decode(errors="replace").strip()

    def section(title, command):
        print("===== " + title + " =====", flush=True)
        p = remote(command)
        print(p.stdout.decode(errors="replace").rstrip(), flush=True)
        if p.returncode:
            print("READ_STATUS=" + str(p.returncode),
                  p.stderr.decode(errors="replace").strip(), flush=True)

    def paths(command, roots):
        p = remote(command)
        if p.returncode:
            print("PATH_LIST_STATUS=" + str(p.returncode),
                  p.stderr.decode(errors="replace").strip(), flush=True)
        return sorted({line.strip() for line in p.stdout.decode(errors="replace").splitlines()
                       if re.fullmatch(r"/[A-Za-z0-9_./@+-]+", line.strip())
                       and ".." not in pathlib.PurePosixPath(line.strip()).parts
                       and any(line.strip().startswith(root + "/") for root in roots)})

    state = run(adb + ["get-state"])
    if state.returncode or state.stdout.strip() != b"device":
        raise SystemExit("ADB device not available")
    model = value("getprop ro.product.model", False)
    fw = value("getprop ro.build.PDA", False)
    if not fw:
        fw = value("getprop ro.build.version.incremental", False)
    print("MODEL=" + model + "\nFIRMWARE=" + fw, flush=True)
    if model != "SM-S948B" or fw != "S948BXXS4BZIG":
        raise SystemExit("REFUSED: inventory must be reviewed for a different firmware")
    if value("getprop sys.boot_completed", False) != "1":
        raise SystemExit("REFUSED: normal boot not completed")
    if value("id -u") != "0" or not value("pidof system_server"):
        raise SystemExit("REFUSED: root read access/stock system_server missing")
    active = remote("pidof xnuhost")
    if active.returncode == 0 or active.stdout.strip():
        raise SystemExit("REFUSED: xnuhost may be active")
    if active.returncode != 1:
        raise SystemExit("REFUSED: unable to verify xnuhost absent")

    section("CPU POLICY (effective readback only)", r"""
for d in /sys/devices/system/cpu/cpufreq/policy*; do
  [ -d "$d" ] || continue
  echo "$d"
  for n in related_cpus cpuinfo_min_freq cpuinfo_max_freq scaling_available_frequencies scaling_min_freq scaling_max_freq scaling_driver scaling_governor; do
    if [ -r "$d/$n" ]; then printf '%s=' "$n"; cat "$d/$n"; fi
  done
done
""")
    section("CANDIDATE SHARED INTERFACES (read only)", r"""
for p in /sys/module/msm_performance/parameters/cpu_max_freq /sys/power/cpufreq_max_limit /sys/power/cpufreq_min_limit /sys/devices/system/cpu/cpufreq_limit/cpufreq_max_limit; do
  [ -e "$p" ] || continue
  ls -l "$p"
  cat "$p" 2>&1
done
""")
    section("PERFORMANCE SERVICES (names and state only)", r"""
echo "extension_library=$(getprop ro.vendor.extension_library)"
service list | grep -iE 'perf|epic|dvfs|power|thermal' || :
getprop | grep -iE '^\[init\.svc\.[^]]*(perf|epic|dvfs|power|thermal)' || :
ps -A -o PID,NAME | grep -iE 'perf|epic|dvfs|power|thermal' || :
""")

    config_roots = ("/vendor/etc", "/odm/etc", "/system_ext/etc", "/product/etc")
    conf = paths(
        "for d in " + " ".join(config_roots) +
        r"""; do [ -d "$d" ] || continue; find "$d" -maxdepth 3 -type f 2>/dev/null | grep -iE '/[^/]*(perf|powerhint|power_hint|epic|dvfs|resourceconfig|targetconfig)[^/]*\.(xml|json|conf|cfg|rc)$' || :; done""",
        config_roots)
    print("===== CONFIG PATHS =====", flush=True)
    print("\n".join(conf) or "(none)", flush=True)
    # Resource mapping files often encode the major/minor indices numerically.
    # Include their complete bounded text, but not unrelated per-app profiles.
    mapping = [p for p in conf if re.search(r"(resourceconfig|targetconfig|perfmapping|resource_mapping)",
                                           pathlib.PurePosixPath(p).name, re.I)]
    for p in mapping[:24]:
        section("RESOURCE MAPPING " + p,
                "head -c 65536 " + shlex.quote(p))
    other = [p for p in conf if p not in mapping]
    for p in other[:32]:
        section("MAX-FREQUENCY MATCHES " + p,
                "grep -iEn -C 2 'cpu.{0,24}max.{0,12}freq|max.{0,12}freq|freq.{0,12}max|cpufreq_limit|FREQ_QOS_MAX|DVFS_MAX|scaling_max_freq' "
                + shlex.quote(p) + " | head -n 120")
    print("MAPPING_FILES_TOTAL=" + str(len(mapping)) +
          " MATCH_FILES_TOTAL=" + str(len(other)), flush=True)

    lib_roots = ("/vendor/lib64", "/odm/lib64", "/system_ext/lib64",
                 "/system/lib64", "/product/lib64")
    libs = paths("for d in " + " ".join(lib_roots) +
                 r"""; do [ -d "$d" ] || continue; find "$d" -maxdepth 2 \( -type f -o -type l \) 2>/dev/null | grep -iE '/[^/]*(perf|epic|dvfs|power)[^/]*\.so$' || :; done""",
                 lib_roots)
    print("===== CANDIDATE LIBRARIES =====", flush=True)
    print("\n".join(libs) or "(none)", flush=True)
    chosen = [p for p in libs if re.search(r"(perf.*client|perfd|libepic|lib.*dvfs|libsemperf|libperf\.so)",
                                          pathlib.PurePosixPath(p).name, re.I)]
    readelf = shutil.which("readelf")
    if not readelf:
        print("STATIC_EXPORTS=SKIPPED_NO_READELF", flush=True)
    else:
        with tempfile.TemporaryDirectory(prefix="oneios-freq-inventory-") as tmp:
            for i, p in enumerate(chosen[:16]):
                print("===== STATIC EXPORTS " + p + " =====", flush=True)
                size = remote("stat -Lc %s " + shlex.quote(p))
                try:
                    n = int(size.stdout.strip())
                except ValueError:
                    n = 0
                if size.returncode or not 0 < n <= 16 * 1024 * 1024:
                    print("SKIP=INVALID_OR_LARGE_ELF", flush=True)
                    continue
                data = remote("cat " + shlex.quote(p), binary=True)
                if data.returncode or len(data.stdout) != n or not data.stdout.startswith(b"\x7fELF"):
                    print("SKIP=READ_FAILED_OR_NOT_ELF", flush=True)
                    continue
                local = pathlib.Path(tmp) / (str(i) + ".so")
                local.write_bytes(data.stdout)
                syms = run([readelf, "--dyn-syms", "--wide", str(local)])
                if syms.returncode:
                    print("SKIP=READELF_FAILED", flush=True)
                    continue
                for line in [l for l in syms.stdout.decode(errors="replace").splitlines()
                             if re.search(r"perf_lock|epic|dvfs|acquire|release|freq|request|perf_hint", l, re.I)
                             and not re.search(r"\bUND\b", l)][:120]:
                    print(line.strip())
    print("STATIC_CANDIDATE_FILES_TOTAL=" + str(len(chosen)), flush=True)
    print("FREQUENCY_INVENTORY=READ_ONLY_COMPLETE")
    print("FREQUENCY_PROVIDER=NOT_QUALIFIED")
    print("DEVICE_WRITES=NONE")


if __name__ == "__main__":
    main()
