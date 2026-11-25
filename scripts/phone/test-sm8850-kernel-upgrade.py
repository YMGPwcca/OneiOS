#!/usr/bin/env python3
"""Local-only tests: no ADB, root writes, Android Framework or watchdog."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from sm8850_kernel_upgrade import CHUNK, CACHE_SHA, NAMES, SIDECARS, digest, make_payload, validate_candidate

HERE = Path(__file__).resolve().parent


def fixture(root):
    stage, local, incoming = root / "stage", root / "local", root / "incoming"
    for path in (stage, stage / "image", stage / "control", stage / "data", local, incoming):
        path.mkdir(mode=0o700)
    def put(path, data):
        path.write_bytes(data)
        path.chmod(0o600)

    old = {"kernel.kc": b"old-kernel", "kernel.kc.hashes": b"old-chunks",
           SIDECARS[0]: b"addon", SIDECARS[1]: b"trustcache", "os.img": b"immutable-apfs"}
    metadata = {"format": 1, "name": "oneios-image", "version": "27.0.1", "build": "24A446",
                "device": "iPhone18,2", "arch": "arm64e", "kernel": "kernel.kc", "chunk": CHUNK,
                "files": [
                    {"path": "kernel.kc", "role": "kernel", "format": "kernel-collection",
                     "read_only": True, "hashes": "kernel.kc.hashes"},
                    {"path": "kernel.kc.hashes", "role": "hashes", "format": "oneios-hash-list-1"},
                    {"path": "os.img", "role": "os", "format": "apfs-raw"}]}
    for entry in metadata["files"]:
        data = old[entry["path"]]
        entry.update(size=len(data), sha256=digest(data))
    old["manifest.json"] = json.dumps(metadata).encode()
    for name, data in old.items():
        put(stage / "image" / name, data)
    old_sha = "".join(f"{digest(old[n])}  {n}\n" for n in sorted(old)).encode()
    old_ids = "".join(subprocess.check_output(["stat", "-c", "%d:%i:%s:%Y",
                     str(stage / "image" / n)], text=True).strip() + "  " + n + "\n"
                     for n in sorted(old)).encode()
    for name, data in (("image.sha256", old_sha), ("image.ids", old_ids),
                       ("image.ready", b"sm8850-ios27-3d-8cpu-600s\n"),
                       ("data.consumed", b"consumed"), ("data/data.img", b"private guest state"),
                       ("runtime.conf", b"xnuhost=bin/xnuhost\n"), ("image.conf", b"format=1\nbuild=24A446\n")):
        put(stage / name, data)
    kernel = struct.pack("<IIII", 0xfeedfacf, 0x0100000c, 2, 12) + b"K" * (CHUNK + 19)
    chunks = struct.pack("<8sIIQQ", b"OIHL1\0\0\0", CHUNK, 1, len(kernel), 2)
    chunks += b"".join(hashlib.sha256(kernel[i:i+CHUNK]).digest() for i in range(0, len(kernel), CHUNK))
    record = {"output": "kernel.kc", "format": "MH_FILESET", "bytes": len(kernel), "sha256": digest(kernel),
              "inputs": {"kernelcache": {"sha256": CACHE_SHA}, "kernel": {"sha256": "1"*64}}}
    put(local / "kernel.kc", kernel)
    put(local / "kernel.kc.hashes", chunks)
    put(local / "kernel.kc.build.json", json.dumps(record).encode())
    candidate = validate_candidate(local / "kernel.kc", local / "kernel.kc.build.json", digest(kernel))
    pins = {n: digest(old[n]) for n in ("kernel.kc", *SIDECARS)}
    return stage, incoming, local, old, old_sha, old_ids, candidate, pins


def prepare(root):
    stage, incoming, local, old, old_sha, old_ids, candidate, pins = fixture(root)
    payload = make_payload(candidate, old["manifest.json"], old_sha, old_ids, pins)
    for name, data in payload.items():
        path = incoming / name
        path.parent.mkdir(mode=0o700, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)
    return stage, incoming, local, old, old_sha, old_ids, candidate, pins


def run_stage(root, shell="sh", fault=False):
    source = (HERE / "framework-stage.sh").read_text()
    actual = source.split("# BEGIN SM8850_KERNEL_UPGRADE\n", 1)[1].split("# END SM8850_KERNEL_UPGRADE", 1)[0]
    actual = actual.replace("= 0:600:1 ]", '= "$TEST_UID:600:1" ]')
    harness = r"""set -eu
umask 077
stage="$TEST_ROOT/stage"
incoming="$TEST_ROOT/incoming"
TEST_UID=$(id -u)
MIN_FREE=0
fail() { echo "STAGING REFUSED: $*" >&2; exit 2; }
root_dir() { [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = "$TEST_UID:700" ]; }
hash_of() { sha256sum "$1" | cut -d' ' -f1; }
getprop() { [ "$1" = init.svc.zygote ] && echo running; }
pidof() { [ "$1" = system_server ] && return 0; return 1; }
df() { printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\nfixture 999999 0 999999 0%% /\n'; }
"""
    if fault:
        harness += r"""mv() {
    case "$1" in "$incoming/new/kernel.kc") return 1 ;; esac
    command mv "$@"
}
"""
    script = root / "harness.sh"
    script.write_text(harness + actual + "\nupgrade_guest_kernel\n")
    return subprocess.run([shell, str(script)], env={**os.environ, "TEST_ROOT": str(root)},
                          capture_output=True, text=True, timeout=30)


class KernelUpgrade(unittest.TestCase):
    def test_candidate_rejects_wrong_hash_chunk_or_record(self):
        with tempfile.TemporaryDirectory() as folder:
            _, _, local, _, _, _, candidate, _ = fixture(Path(folder))
            kc, rec = local / "kernel.kc", local / "kernel.kc.build.json"
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                validate_candidate(kc, rec, "0"*64)
            (local / "kernel.kc.hashes").write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "chunk list"):
                validate_candidate(kc, rec, digest(candidate["kernel.kc"]))
            (local / "kernel.kc.hashes").write_bytes(candidate["kernel.kc.hashes"])
            record = json.loads(rec.read_bytes())
            record["inputs"]["kernelcache"]["sha256"] = "0"*64
            rec.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "24A446"):
                validate_candidate(kc, rec, digest(candidate["kernel.kc"]))

    def test_manifest_changes_only_kernel_entries_and_requires_sidecar_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            _, _, _, old, sha, ids, candidate, pins = fixture(Path(folder))
            payload = make_payload(candidate, old["manifest.json"], sha, ids, pins)
            before = json.loads(old["manifest.json"])
            after = json.loads(payload["new/manifest.json"])
            for entry in after["files"][:2]:
                n = entry["path"]
                self.assertEqual(entry["sha256"], digest(candidate[n]))
            after["files"][:2] = before["files"][:2]
            self.assertEqual(before, after)
            with self.assertRaisesRegex(ValueError, "Unexpected installed pin"):
                make_payload(candidate, old["manifest.json"], sha, ids, {**pins, SIDECARS[0]: "0"*64})

    def test_real_stage_function_preserves_data_sidecars_and_old_inodes(self):
        for shell in filter(None, (shutil.which("sh"), shutil.which("bash"), shutil.which("mksh"))):
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                stage, _, _, old, sha, ids, candidate, _ = prepare(root)
                result = run_stage(root, shell)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("KERNEL_UPGRADE=PASS_BACKUP_PRESERVED:", result.stdout)
                archive, = (stage / ".rollback").glob("kernel.*")
                for name in NAMES:
                    self.assertEqual((archive / "image" / name).read_bytes(), old[name])
                self.assertEqual((archive / "image.sha256").read_bytes(), sha)
                self.assertEqual((archive / "image.ids").read_bytes(), ids)
                self.assertEqual((stage / "image/kernel.kc").read_bytes(), candidate["kernel.kc"])
                for name in (*SIDECARS, "os.img"):
                    self.assertEqual((stage / "image" / name).read_bytes(), old[name])
                self.assertEqual((stage / "data/data.img").read_bytes(), b"private guest state")
                self.assertEqual((stage / "data.consumed").read_bytes(), b"consumed")
                self.assertTrue((stage / "image.ready").is_file())
                self.assertFalse((stage / "image.ready.kernel-pending").exists())

    def test_tampered_sidecar_refuses_before_disarm(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage, _, _, old, _, _, _, _ = prepare(root)
            path = stage / "image" / SIDECARS[0]
            st = path.stat()
            path.write_bytes(b"wrong")
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
            result = run_stage(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((stage / "image.ready").is_file())
            self.assertFalse((stage / ".rollback").exists())
            self.assertEqual((stage / "image/kernel.kc").read_bytes(), old["kernel.kc"])

    def test_interrupted_publication_disarms_and_preserves_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stage, _, _, old, _, _, _, _ = prepare(root)
            result = run_stage(root, fault=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((stage / "image.ready").exists())
            self.assertTrue((stage / "image.ready.kernel-pending").exists())
            archive, = (stage / ".rollback").glob("kernel.*")
            self.assertEqual((archive / "image/kernel.kc").read_bytes(), old["kernel.kc"])


if __name__ == "__main__":
    unittest.main()
