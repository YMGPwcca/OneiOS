#!/usr/bin/env python3
"""Guarded, one-way SM8850 APFS Data clone; no iOS guest boot or takeover.

'snapshot' allocates a private candidate copy but never changes the bench input.
The candidate alone does NOT authorize a guest launch.
"""

import argparse
import hashlib
import importlib.util
import json
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BENCH_DATA = "/data/local/tmp/oneios-m3q-ios27-bench/data"
PREFIX = "/data/adb/oneios-m3q-gpu-snapshot-"
UPLOAD_PREFIX = "/data/local/tmp/oneios-m3q-gpu-copy-"
SOURCE = ROOT / "scripts/phone/framework-image-copy.c"
MIN_AFTER_KIB = 30 * 1024 * 1024 + 65536
EXPECTED_DATA_BYTES = 8 * 1024**3
STAGE_ALLOW = re.compile(r"[a-f0-9]{16}\Z")


def load_tool(filename, module_name):
    path = HERE / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"missing tool: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unique_paths(nonce):
    if STAGE_ALLOW.fullmatch(nonce) is None:
        raise ValueError("invalid snapshot nonce")
    return PREFIX + nonce, UPLOAD_PREFIX + nonce


def device_script(nonce, expected_helper_sha256, expected_data_sha256=None, expected_chip_sha256=None, *, compact=False):
    """Static, restricted device script: no user-provided paths or shell words."""
    stage, incoming = unique_paths(nonce)
    if not re.fullmatch(r"[a-f0-9]{64}", expected_helper_sha256):
        raise ValueError("invalid helper digest")
    for digest in (expected_data_sha256, expected_chip_sha256):
        if digest is not None and not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("invalid expected source hash")
    # This script is executed only under su, after an independent passive preflight.
    return f'''set -eu
umask 077
STAGE='{stage}'
INCOMING='{incoming}'
BASE='{BENCH_DATA}'
MIN_AFTER={MIN_AFTER_KIB}
fail() {{ printf 'SNAPSHOT_ERROR=%s\\n' "$*" >&2; exit 2; }}
[ "$(id -u)" = 0 ] || fail 'requires root'
[ "$(getprop sys.boot_completed)" = 1 ] || fail 'Framework not booted'
[ "$(getenforce)" = Enforcing ] || fail 'SELinux not enforcing'
[ "$(getprop ro.product.model):$(getprop ro.product.device):$(getprop ro.soc.model)" = SM-S948B:m3q:SM8850 ] || fail 'device mismatch'
[ "$(getprop ro.build.version.incremental)" = S948BXXS4BZIG ] || fail 'firmware mismatch'
[ "$(getprop init.svc.zygote)" = running ] && pidof system_server >/dev/null 2>&1 || fail 'Framework unhealthy'
if pidof xnuhost xnuhost-gui-bench xnuhost-tasks oneios-display OneiOSDisplay >/dev/null 2>&1; then fail 'guest is running'; fi
[ "$(stat -c '%u:%a' /data/adb)" = 0:700 ] || fail 'untrusted /data/adb owner or mode'
[ ! -e "$STAGE" ] && [ ! -L "$STAGE" ] || fail 'snapshot already exists'
[ -f "$INCOMING" ] && [ ! -L "$INCOMING" ] || fail 'helper upload missing'
[ "$(sha256sum "$INCOMING" | cut -d ' ' -f1)" = '{expected_helper_sha256}' ] || fail 'helper upload changed'
[ -f "$BASE/data.img" ] && [ ! -L "$BASE/data.img" ] || fail 'original Data missing'
[ -f "$BASE/unique-chip-id" ] && [ ! -L "$BASE/unique-chip-id" ] || fail 'original chip ID missing'
[ "$(stat -c '%s:%h' "$BASE/data.img")" = {EXPECTED_DATA_BYTES}:1 ] || fail 'original Data size or links changed'
[ "$(stat -c '%s:%h' "$BASE/unique-chip-id")" = 8:1 ] || fail 'original chip ID size or links changed'
free=$(df -Pk /data/adb | awk 'END {{print $4}}')
{('[ "$free" -ge "$((MIN_AFTER + 2097152))" ] || fail "less than reserve + compact copy margin"' if compact else '[ "$free" -ge "$((MIN_AFTER + 10485760))" ] || fail "less than 30GiB reserve + 10GiB clone budget"')}
orig_data_stat=$(stat -c '%d:%i:%s:%Y:%Z' "$BASE/data.img")
orig_chip_stat=$(stat -c '%d:%i:%s:%Y:%Z' "$BASE/unique-chip-id")
orig_data_sha=$(sha256sum "$BASE/data.img" | cut -d ' ' -f1)
orig_chip_sha=$(sha256sum "$BASE/unique-chip-id" | cut -d ' ' -f1)
{f'[ "$orig_data_sha" = "{expected_data_sha256}" ] || fail "source Data differs from supplied independent hash"' if expected_data_sha256 else ':'}
{f'[ "$orig_chip_sha" = "{expected_chip_sha256}" ] || fail "chip ID differs from supplied independent hash"' if expected_chip_sha256 else ':'}
[ "$orig_data_stat" = "$(stat -c '%d:%i:%s:%Y:%Z' "$BASE/data.img")" ] || fail 'source changed during hash'
mkdir -m 700 "$STAGE" || fail 'cannot create root-owned private snapshot'
printf 'STAGE_PATH=%s\\n' "$STAGE"
mkdir -m 700 "$STAGE/data" "$STAGE/bin"
cp "$INCOMING" "$STAGE/bin/copy"
chmod 700 "$STAGE/bin/copy"
[ "$(sha256sum "$STAGE/bin/copy" | cut -d ' ' -f1)" = '{expected_helper_sha256}' ] || fail 'helper staged digest mismatch'
( set -C; : > "$STAGE/data/data.img" ) || fail 'snapshot destination already exists'
timeout -s TERM 900 "$STAGE/bin/copy" {'compact' if compact else 'sparse'} "$BASE/data.img" "$STAGE/data/data.img" || fail 'bounded Data copy failed (see compact required bytes if present)'
cp "$BASE/unique-chip-id" "$STAGE/data/unique-chip-id"
chmod 600 "$STAGE/data/data.img" "$STAGE/data/unique-chip-id"
snapshot_data_sha=$(sha256sum "$STAGE/data/data.img" | cut -d ' ' -f1)
snapshot_chip_sha=$(sha256sum "$STAGE/data/unique-chip-id" | cut -d ' ' -f1)
source_data_again=$(sha256sum "$BASE/data.img" | cut -d ' ' -f1)
source_chip_again=$(sha256sum "$BASE/unique-chip-id" | cut -d ' ' -f1)
[ "$orig_data_sha" = "$snapshot_data_sha" ] && [ "$orig_data_sha" = "$source_data_again" ] || fail 'Data hash mismatch or concurrent original write'
[ "$orig_chip_sha" = "$snapshot_chip_sha" ] && [ "$orig_chip_sha" = "$source_chip_again" ] || fail 'chip ID hash mismatch or concurrent original write'
[ "$orig_data_stat" = "$(stat -c '%d:%i:%s:%Y:%Z' "$BASE/data.img")" ] || fail 'original Data stat changed'
[ "$orig_chip_stat" = "$(stat -c '%d:%i:%s:%Y:%Z' "$BASE/unique-chip-id")" ] || fail 'original chip ID stat changed'
[ "$(stat -c '%s:%h' "$STAGE/data/data.img")" = {EXPECTED_DATA_BYTES}:1 ] || fail 'clone size or hardlink count invalid'
[ "$(stat -c '%s:%h' "$STAGE/data/unique-chip-id")" = 8:1 ] || fail 'cloned chip ID invalid'
[ "$(stat -c '%d:%i' "$BASE/data.img")" != "$(stat -c '%d:%i' "$STAGE/data/data.img")" ] || fail 'Data clone shares original inode'
free_after=$(df -Pk /data/adb | awk 'END {{print $4}}')
[ "$free_after" -ge "$MIN_AFTER" ] || fail '30GiB reserve crossed'
printf 'data_sha256=%s\\nchip_sha256=%s\\n' "$snapshot_data_sha" "$snapshot_chip_sha" > "$STAGE/source-verified.sha256.txt.tmp"
mv "$STAGE/source-verified.sha256.txt.tmp" "$STAGE/source-verified.sha256.txt"
chmod 600 "$STAGE/source-verified.sha256.txt"
printf 'SOURCE_DATA_SHA256=%s\\n' "$orig_data_sha"
printf 'SNAPSHOT_DATA_SHA256=%s\\n' "$snapshot_data_sha"
printf 'SOURCE_CHIP_SHA256=%s\\n' "$orig_chip_sha"
printf 'SNAPSHOT_CHIP_SHA256=%s\\n' "$snapshot_chip_sha"
printf 'FREE_AFTER_KIB=%s\\n' "$free_after"
printf 'DATA_CLONE_READY=PASS\\n'
printf 'GUEST_RUN_READY=BLOCKED\\n'
'''


def parse_success(stdout, stage):
    values = {}
    for line in stdout.splitlines():
        if '=' not in line:
            continue
        name, val = line.split('=', 1)
        if name in {'STAGE_PATH', 'SOURCE_DATA_SHA256', 'SNAPSHOT_DATA_SHA256',
                    'SOURCE_CHIP_SHA256', 'SNAPSHOT_CHIP_SHA256', 'FREE_AFTER_KIB',
                    'DATA_CLONE_READY', 'GUEST_RUN_READY'}:
            if name in values:
                raise ValueError('duplicate snapshot status: ' + name)
            values[name] = val
    if (values.get('STAGE_PATH') != stage or
        values.get('DATA_CLONE_READY') != 'PASS' or
        values.get('GUEST_RUN_READY') != 'BLOCKED'):
        raise ValueError('snapshot did not report complete verification')
    for key in ('SOURCE_DATA_SHA256', 'SNAPSHOT_DATA_SHA256', 'SOURCE_CHIP_SHA256', 'SNAPSHOT_CHIP_SHA256'):
        if not re.fullmatch('[a-f0-9]{64}', values.get(key, '')):
            raise ValueError('missing digest: ' + key)
    if (values['SOURCE_DATA_SHA256'] != values['SNAPSHOT_DATA_SHA256'] or
        values['SOURCE_CHIP_SHA256'] != values['SNAPSHOT_CHIP_SHA256']):
        raise ValueError('source and copy do not match')
    free = values.get('FREE_AFTER_KIB', '')
    if not free.isdigit() or int(free) < MIN_AFTER_KIB:
        raise ValueError('not enough free space after snapshot')
    return values


def compile_copy_helper(output):
    ndk = Path(__import__('os').environ.get('ANDROID_NDK_ROOT', Path.home() / 'Android/Sdk/ndk/28.2.13676358'))
    cc = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang'
    subprocess.run([str(cc), '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                    str(SOURCE), '-o', str(output)], check=True, timeout=90)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('plan', 'snapshot'))
    p.add_argument('--adb', default=shutil.which('adb') or str(Path.home() / 'Android/Sdk/platform-tools/adb'))
    p.add_argument('--serial')
    p.add_argument('--compact', action='store_true', help='snapshot only: measure nonzero 4KiB payload before allocating, retain reserve and margin')
    p.add_argument('--expected-data-sha256', help='optional independent off-device Data hash pin')
    p.add_argument('--expected-chip-sha256', help='optional independent off-device chip-ID hash pin')
    p.add_argument('--output', type=Path)
    args = p.parse_args(argv)
    if args.compact and args.action != 'snapshot':
        p.error('--compact requires snapshot; ordinary plan retains full logical-size budget')
    out = args.output or ROOT / 'out/sm8850/gpu-acceptance' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-data-' + args.action + '.json')
    report = {'action': args.action, 'GUEST_RUN_READY': 'BLOCKED',
              'scope': 'isolated Data snapshot only; no iOS guest, Framework takeover or watchdog operations'}
    status = 0
    stage = None
    try:
        harness = load_tool('sm8850-gpu-acceptance.py', 'oneios_gpu_acceptance')
        readiness = load_tool('sm8850-ios-gpu-readiness.py', 'oneios_ios_readiness')
        adb = harness.select_usb(args.adb, args.serial)
        vals = harness.decode_kv(harness.root(adb, harness.DEVICE_AUDIT).stdout)
        checks, failures = harness.validate_preflight(vals)
        report['preflight'] = {'checks': checks, 'values': vals, 'failures': failures}
        if failures:
            raise ValueError('preflight failed: ' + ', '.join(failures))
        inv = readiness.parse_asset_audit(harness.root(adb, readiness.DEVICE_ASSET_AUDIT, seconds=120).stdout)
        assessment = readiness.evaluate_inventory(vals, inv)
        report['readiness'] = assessment
        required = ('source_complete', 'data_pair_sizes', 'data_pair_single_link')
        if not all(assessment.get(k) for k in required):
            raise ValueError('Data source is not qualified')
        if args.compact:
            if assessment['available_kib'] < MIN_AFTER_KIB + readiness.CLONE_MARGIN_KIB:
                raise ValueError('less than 30GiB reserve + compact copy margin')
            report['copy_mode'] = 'compact_measured_payload'
        elif not assessment['projected_clone_space']:
            raise ValueError('30GiB reserve + clone budget is not qualified')
        print('PREFLIGHT=PASS')
        if args.action == 'plan':
            print('COPY_ADMISSION=PASS; SNAPSHOT_NOT_CREATED')
            print('GUEST_RUN_READY=BLOCKED')
            return 0
        nonce = secrets.token_hex(8)
        stage, incoming = unique_paths(nonce)
        report['stage_path'] = stage
        with tempfile.TemporaryDirectory(prefix='oneios-data-clone-') as tmp:
            helper = Path(tmp) / 'copy'
            helper_sha = compile_copy_helper(helper)
            report['helper_sha256'] = helper_sha
            # Phone-side namespace is a nonce-specific *new* path; the original bench is read-only.
            try:
                harness.run([*adb, 'push', str(helper), incoming], seconds=90)
                script = device_script(nonce, helper_sha, args.expected_data_sha256, args.expected_chip_sha256,
                                       compact=args.compact)
                outcome = harness.root(adb, script, seconds=1800, check=False)
                report['device_exit'] = outcome.returncode
                report['device_log_tail'] = outcome.stdout[-6000:]
                if args.compact:
                    for line in outcome.stdout.splitlines():
                        if re.fullmatch(r"COMPACT_(?:NONZERO_BYTES|REQUIRED_FREE_BYTES|WRITTEN_BYTES)=\d+", line):
                            print(line, flush=True)
                if outcome.returncode:
                    raise ValueError('device snapshot failed; partial private stage preserved (exit ' + str(outcome.returncode) + ')')
                report['verification'] = parse_success(outcome.stdout, stage)
                report['DATA_CLONE_READY'] = 'PASS'
                print('DATA_CLONE_READY=PASS')
                print('STAGE_PATH=' + stage)
                print('GUEST_RUN_READY=BLOCKED')
            finally:
                try:
                    # Only the exact nonce upload is removed; the source and private stage are retained.
                    harness.root(adb, f"rm -f '{incoming}'", seconds=15)
                except Exception as exc:
                    report['upload_cleanup_warning'] = str(exc)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        status = 2
        report['error'] = str(exc)
        print('BLOCKED: ' + str(exc), file=sys.stderr)
    finally:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        print('REPORT=' + str(out))
    return status


if __name__ == '__main__':
    sys.exit(main())
