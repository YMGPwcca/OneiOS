"""Negative and positive tests for the local boot compatibility gate."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

import fixtures


ROOT = Path(__file__).resolve().parents[3]
CHECK = ROOT / "scripts/image/verify-boot.py"
TOOL = Path(os.environ.get("ONEIOS_TOOL", ROOT / "tools/oneios-tool/target/release/oneios-tool"))


def digest(path, algorithm="sha256"):
    return hashlib.new(algorithm, path.read_bytes()).hexdigest()


class VerifyBootTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.image = self.root / "image"
        self.image.mkdir()
        self.runtime = self.root / "runtime"
        (self.runtime / "bin").mkdir(parents=True)
        _, profile, originals = fixtures.fake_ipsw(str(self.root / "inputs"))
        self.profile = Path(profile)
        data = tomllib.loads(self.profile.read_text())
        self.kernel_profile = self.root / "kernel-profile.toml"
        self.kernel_profile.write_text('[ipsw]\nbuild = "0T1"\nproduct = "iTest1,1"\n'
                                       f'[kernel.prelink]\nkernelcache_sha256 = "{"a" * 64}"\n')
        # The directory verifier and APFS parser are real. The loader's
        # independent integration run uses the genuine 24A446 collection.
        self.loader = self.root / "fixture-loader"
        self.loader.write_text("#!/bin/sh\nprintf 'MH_FILESET arm64e fixture\\n'\n")
        self.loader.chmod(0o755)
        for member in data["member"]:
            role = member["role"]
            if role not in data["image"]["files"]:
                continue
            file = self.image / data["image"]["files"][role]
            file.parent.mkdir(exist_ok=True)
            if member.get("aea"):
                fixtures.fake_apfs(file, role)
            else:
                file.write_bytes(originals[member["path"]])
        self.kernel = self.image / "kernel.kc"
        self.kernel.write_bytes(b"synthetic kernel bytes")
        (self.image / "data.seed").write_bytes(bytes(1024))
        self.build_record = self.root / "kernel.kc.build.json"
        self.write_json(self.build_record, {
            "format": "MH_FILESET", "output": "kernel.kc", "bytes": self.kernel.stat().st_size,
            "sha256": digest(self.kernel), "releasable": False,
            "inputs": {"kernelcache": {"sha256": "a" * 64}, "kernel": {"sha256": "b" * 64}},
        })
        binary = self.runtime / "bin/xnuhost"
        binary.write_bytes(bytes.fromhex("7f454c460201010000000000000000000200b700") + bytes(64))
        binary.chmod(0o755)
        self.runtime_manifest = self.runtime / "runtime.json"
        self.write_json(self.runtime_manifest, {
            "name": "oneios-runtime", "arch": "arm64", "format": 1, "session_abi": 1,
            "image_formats": [1], "placeholder": False, "xnuhost": "bin/xnuhost",
            "files": [{"path": "bin/xnuhost", "size": binary.stat().st_size,
                       "sha256": digest(binary), "mode": "0755"}],
        })
        self.manifest = self.image / "manifest.json"
        self.tool("manifest", self.profile, self.image)

    def tool(self, *args):
        return subprocess.run([TOOL, "image", *args], check=True, capture_output=True, text=True)

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value))

    def change(self, path, edit):
        data = json.loads(path.read_text())
        edit(data)
        self.write_json(path, data)

    def check(self, message=None, *extra):
        p = subprocess.run(
            ["python3", CHECK, self.image, "--runtime", self.runtime, "--profile", self.profile,
             "--kernel-profile", self.kernel_profile, "--kernel-record", self.build_record,
             "--tool", TOOL, "--loader", self.loader, *extra], capture_output=True, text=True,
        )
        if message:
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn(message, p.stderr)
        else:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(json.loads(p.stdout)["scope"], "local-artifact-compatibility")

    def test_complete_set_and_matching_archive(self):
        archive = self.root / "verified.tar.zst"
        self.tool("pack", self.image, archive)
        self.check(None, "--archive", archive)

    def test_missing_image_file(self):
        (self.image / "os.img").unlink()
        self.check("missing os.img")

    def test_malformed_manifest(self):
        self.manifest.write_text("{")
        self.check("manifest.json")

    def test_manifest_file_exceeds_oneos_limit(self):
        self.change(self.manifest, lambda d: d["files"][0].update(size=(16 << 30) + 1))
        self.check("invalid file size")

    def test_rehashed_wrong_kernel_cannot_match_independent_build_record(self):
        self.kernel.write_bytes(b"a different kernel")
        self.tool("manifest", self.profile, self.image)
        self.check("kernel collection differs from the build record")

    def test_kernel_record_for_a_different_vendor_cache(self):
        self.change(self.build_record, lambda d: d["inputs"]["kernelcache"].update(sha256="c" * 64))
        self.check("kernelcache pin")

    def test_abi_mismatch(self):
        self.change(self.runtime_manifest, lambda d: d.update(session_abi=2))
        self.check("session ABI 1")

    def test_runtime_binary_hash_mismatch(self):
        binary = self.runtime / "bin/xnuhost"
        binary.write_bytes(binary.read_bytes()[:-1] + b"!")
        self.check("runtime bin/xnuhost: SHA-256 differs")

    def test_unsupported_image_formats(self):
        self.change(self.runtime_manifest, lambda d: d.update(image_formats=[2]))
        self.check("does not support image format 1")
        self.change(self.manifest, lambda d: d.update(format=2))
        self.check("image format")

    def test_missing_trustcache_manifest_entry(self):
        path = "trust/system.trustcache"
        (self.image / path).unlink()
        self.change(self.manifest, lambda d: d.update(files=[x for x in d["files"] if x["path"] != path]))
        self.check("required file " + path)

    def test_invalid_whole_file_and_chunk_hashes(self):
        image = self.image / "os.img"
        with image.open("r+b") as stream:
            stream.seek(-1, os.SEEK_END)
            stream.write(b"1")
        self.check("SHA-256 differs")
        self.tool("manifest", self.profile, self.image)
        hashes = self.image / "os.img.hashes"
        with hashes.open("r+b") as stream:
            stream.seek(-1, os.SEEK_END)
            value = stream.read(1)[0]
            stream.seek(-1, os.SEEK_END)
            stream.write(bytes([value ^ 1]))
        self.change(self.manifest, lambda d: next(e for e in d["files"]
                    if e["path"] == "os.img.hashes").update(sha256=digest(hashes)))
        self.check("chunk")

    def test_rehashed_trustcache_still_has_to_match_release_member(self):
        cache = self.image / "trust/static.trustcache"
        cache.write_bytes(cache.read_bytes()[:-1] + b"!")
        self.tool("manifest", self.profile, self.image)
        self.check("SHA-384 differs from the profile")

    def test_apfs_metadata_must_match_the_volume(self):
        self.change(self.manifest, lambda d: next(e for e in d["files"]
                    if e["path"] == "os.img")["apfs"].update(volumes=[]))
        self.check("APFS metadata differs")

    def test_different_valid_archive_and_corrupted_archive(self):
        archive = self.root / "different.tar.zst"
        self.tool("pack", self.image, archive)
        (self.image / "data.seed").write_bytes(bytes(1024) + b"changed")
        self.tool("manifest", self.profile, self.image)
        self.check("archive manifest differs", "--archive", archive)
        archive.write_bytes(archive.read_bytes()[:64])
        self.check("archive", "--archive", archive)


if __name__ == "__main__":
    unittest.main()
