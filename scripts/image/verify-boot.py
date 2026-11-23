#!/usr/bin/env python3
"""Verify an unpacked image/runtime pair before attempting a local guest boot."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import tomllib


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_LIMIT = 4 << 20  # The limit xnuhost uses for its image manifest.
FILE_LIMIT = 16 << 30     # OneOS's per-file image-set limit.
VOLUMES = {"os", "systemos", "app"}


class Invalid(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Invalid(reason)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"JSON key {key!r} is repeated")
        result[key] = value
    return result


def metadata(path):
    try:
        with path.open("rb") as stream:
            raw = stream.read(MANIFEST_LIMIT + 1)
        require(len(raw) <= MANIFEST_LIMIT, "metadata exceeds the size limit")
        value = json.loads(raw, object_pairs_hook=unique_object)
        require(isinstance(value, dict), "expected a JSON object")
    except (Invalid, ValueError, OSError) as error:
        raise Invalid(f"{path}: {error}") from error
    return value, raw


def sha(path, algorithm="sha256"):
    with path.open("rb") as file:
        return hashlib.file_digest(file, algorithm).hexdigest()


def hex64(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[a-f0-9]{64}", value))


def file_index(manifest):
    entries = {}
    for entry in manifest["files"]:
        name = entry["path"]
        require(isinstance(name, str) and all(
            component not in ("", ".", "..") for component in name.split("/")
        ) and not re.search(r"[\\\x00-\x1f]", name), f"unsafe file path {name!r}")
        require(name not in entries, f"{name} is listed twice")
        require(type(entry["size"]) is int and 0 < entry["size"] <= FILE_LIMIT, f"{name}: invalid file size")
        require(hex64(entry["sha256"]), f"{name}: invalid SHA-256")
        entries[name] = entry
    return entries


def expected_file(entries, name, role):
    require(name in entries, f"missing required file {name}")
    entry = entries[name]
    require(entry.get("role") == role, f"{name}: expected role {role}")
    return entry


def hash_list(entries, name, entry):
    expected = name + ".hashes"
    require(entry.get("hashes") == expected, f"{name}: missing or mismatched chunk hash list")
    require(expected_file(entries, expected, "hashes").get("format") == "oneios-hash-list-1",
            f"{expected}: unsupported hash list format")


def check_identity(image, profile, profile_path):
    require(image.get("name") == "oneios-image", "not a OneiOS image manifest")
    require(type(image.get("format")) is int and image["format"] == profile["image"]["format"] == 1,
            "unsupported image format")
    for key in ("version", "build", "device", "board", "arch", "chip_id", "board_id"):
        require(image.get(key) == profile["os"][key], f"image {key} differs from the profile")
    require(image["profile"]["sha256"] == sha(profile_path), "image was not built with this profile")
    source = {f"ipsw_{key}": profile["ipsw"][key] for key in ("url", "size", "sha256")}
    require(image.get("source") == source, "image source differs from the pinned IPSW")
    require(image.get("chunk") == profile["image"]["chunk"], "image chunk size differs from the profile")
    require(image.get("stage") == profile["image"]["stage"], "image stage path differs from the profile")


def check_runtime(root, runtime, image_format):
    require(runtime.get("name") == "oneios-runtime" and runtime.get("format") == 1 and
            runtime.get("arch") == "arm64", "not a format 1 arm64 OneOS runtime")
    require(type(runtime.get("session_abi")) is int and runtime["session_abi"] == 1,
            "runtime must implement session ABI 1")
    formats = runtime.get("image_formats")
    require(isinstance(formats, list) and any(type(f) is int and f == image_format for f in formats),
            f"runtime does not support image format {image_format}")
    require(runtime.get("placeholder") is False, "runtime is a placeholder or lacks its build declaration")
    name = runtime["xnuhost"]
    entries = file_index(runtime)
    require(name in entries and entries[name].get("mode") == "0755", "runtime has no listed executable xnuhost")
    present = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_symlink() or not path.is_dir()}
    require(present == set(entries) | {"runtime.json"}, "runtime files differ from the manifest list")
    for rel, entry in entries.items():
        path = root / rel
        # Reject symlinks anywhere in a listed path, before opening its target.
        parent = path
        while parent != root:
            require(not parent.is_symlink(), f"runtime {rel}: symbolic link")
            parent = parent.parent
        require(path.is_file() and path.stat().st_size == entry["size"], f"runtime {rel}: missing or wrong size")
        require(sha(path) == entry["sha256"], f"runtime {rel}: SHA-256 differs")
    binary = root / name
    with binary.open("rb") as stream:
        header = stream.read(20)
    require(header[:6] == b"\x7fELF\x02\x01" and header[18:20] == b"\xb7\x00" and
            binary.stat().st_mode & stat.S_IXUSR, "xnuhost is not an executable little-endian arm64 ELF")
    return entries[name]["sha256"]


def run(*command):
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise Invalid((result.stderr or result.stdout).strip() or f"{command[0]} exited {result.returncode}")
    return result.stdout.strip()


def check_archive(path, image_raw, tool):
    sidecar = Path(f"{path}.sha256")
    require(sidecar.is_file(), "archive is missing its SHA-256 sidecar")
    fields = sidecar.read_text().split()
    require(len(fields) == 2 and hex64(fields[0]) and fields[1] == path.name,
            "archive SHA-256 sidecar is malformed")
    # Bound the decompression window to the OneOS app's format contract.
    try:
        run("zstd", "-q", "-t", "--long=27", "--", path)
    except Invalid as error:
        raise Invalid(f"archive decompression failed: {error}") from error
    with subprocess.Popen(["zstd", "-q", "-dc", "--long=27", "--", path],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as decoder:
        try:
            header = tarfile.TarInfo.frombuf(decoder.stdout.read(512), "utf-8", "strict")
            require(header.name == "manifest.json" and header.isfile() and
                    0 < header.size <= MANIFEST_LIMIT, "archive must start with a bounded regular manifest.json")
            require(decoder.stdout.read(header.size) == image_raw, "archive manifest differs from the checked image")
        except (tarfile.HeaderError, UnicodeError) as error:
            raise Invalid(f"archive first header is invalid: {error}") from error
        finally:
            # This pass only needs the first member. The full reader below
            # checks the rest of the stream without extracting any file.
            decoder.stdout.close()
            if decoder.poll() is None:
                decoder.kill()
    run(tool, "image", "verify", path)
    return fields[0]


def verify(args):
    image, image_raw = metadata(args.image / "manifest.json")
    runtime, runtime_raw = metadata(args.runtime / "runtime.json")
    record, record_raw = metadata(args.kernel_record)
    profile = tomllib.loads(args.profile.read_text())
    kernel_profile = tomllib.loads(args.kernel_profile.read_text())
    check_identity(image, profile, args.profile)
    xnuhost_digest = check_runtime(args.runtime, runtime, image["format"])
    entries = file_index(image)
    name = profile["image"]["kernel"]
    kernel = expected_file(entries, name, "kernel")
    require(image.get("kernel") == name and kernel.get("format") == "kernel-collection",
            "image has no supported kernel collection declaration")
    hash_list(entries, name, kernel)
    require(record["output"] == name and record["format"] == "MH_FILESET" and
            record["bytes"] == kernel["size"] and record["sha256"] == kernel["sha256"],
            "kernel collection differs from the build record")
    vendor_digest = kernel_profile["kernel"]["prelink"]["kernelcache_sha256"]
    require(kernel_profile["ipsw"]["build"] == image["build"] and
            kernel_profile["ipsw"]["product"] == image["device"] and
            hex64(vendor_digest) and record["inputs"]["kernelcache"]["sha256"] == vendor_digest and
            hex64(record["inputs"]["kernel"]["sha256"]), "kernel build record differs from the kernelcache pin")

    seed = profile["image"]["seed"]
    data = image["data"]
    require(data["seed"] == seed and data["volume_uuid"] == profile["data"]["volume_uuid"].upper() and
            data["volume_name"] == profile["data"].get("volume_name", "Data") and data["case_sensitive"] is True,
            "Data seed or volume identity differs from the profile")
    seed_entry = expected_file(entries, seed, "data-seed")
    require(seed_entry.get("format") in {"tar", "apfs-raw"}, "unsupported Data seed format")
    members = {member["role"]: member for member in profile["member"]}
    fetch = metadata(args.inputs_record)[0] if args.inputs_record else None
    if fetch:
        require(fetch["build"] == image["build"], "inputs record is for another build")
    for role, path in profile["image"]["files"].items():
        entry = expected_file(entries, path, role)
        member = members[role]
        require(entry["source"]["member"] == member["path"] and
                entry["source"]["decrypted"] is bool(member.get("aea")), f"{path}: incorrect firmware provenance")
        if role in VOLUMES:
            require(entry.get("format") == "apfs-raw" and entry.get("read_only") is True, f"{path}: expected read-only raw APFS")
            hash_list(entries, path, entry)
        else:
            expected_format = "img4-payload" if role.startswith("trust-") else "root-hash"
            require(entry.get("format") == expected_format, f"{path}: expected {expected_format}")
        if fetch and member.get("aea"):
            plain = fetch["members"][role]
            require(plain["member"] == member["path"] and plain["plain_size"] == entry["size"] and
                    plain["plain_sha256"] == entry["sha256"], f"{path}: differs from the decrypted inputs record")

    integrity = run(args.tool, "image", "verify", args.image)
    first_line = run(args.loader, "kernel", args.image / name).splitlines()[0]
    require(first_line.startswith("MH_FILESET " + profile["os"]["arch"] + " "), "loader did not find the expected kernel fileset")
    for role, path in profile["image"]["files"].items():
        member = members[role]
        if "sha384" in member:
            require(sha(args.image / path, "sha384") == member["sha384"], f"{path}: SHA-384 differs from the profile")
        if role in VOLUMES:
            found = json.loads(run(args.tool, "image", "apfs-info", args.image / path))
            require(found == entries[path]["apfs"] and found["volumes"], f"{path}: APFS metadata differs from the manifest")

    return {
        "status": "PASS", "scope": "local-artifact-compatibility", "build": image["build"],
        "device": image["device"], "image_format": 1, "session_abi": 1,
        "image_manifest_sha256": hashlib.sha256(image_raw).hexdigest(),
        "runtime_manifest_sha256": hashlib.sha256(runtime_raw).hexdigest(),
        "xnuhost_sha256": xnuhost_digest, "kernel_sha256": kernel["sha256"],
        "kernel_record_sha256": hashlib.sha256(record_raw).hexdigest(), "kernelcache_sha256": vendor_digest,
        "inputs_record_sha256": sha(args.inputs_record) if args.inputs_record else None,
        "archive_sha256": check_archive(args.archive, image_raw, args.tool) if args.archive else None,
        "integrity": integrity, "loader": first_line,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--runtime", type=Path, required=True, help="Unpacked source-built runtime")
    parser.add_argument("--kernel-record", type=Path, required=True, help="Independent kernel.kc.build.json from prelink")
    parser.add_argument("--inputs-record", type=Path, help="inputs.json produced by fetch and AEA decryption")
    parser.add_argument("--archive", type=Path, help="Optional .tar.zst of this same image directory")
    parser.add_argument("--profile", type=Path, default=ROOT / "profiles/ios-27.0.1-iPhone18,2.toml")
    parser.add_argument("--kernel-profile", type=Path, default=ROOT / "kernel/unixnu/profiles/os/ios-27.0.1-24A446/profile.toml")
    parser.add_argument("--tool", type=Path, default=Path(os.environ.get(
        "ONEIOS_TOOL", ROOT / "tools/oneios-tool/target/release/oneios-tool")))
    parser.add_argument("--loader", type=Path, default=ROOT / "runtime/loader/build/host/xnuloader-inspect")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args), indent=2))
    except (Invalid, OSError, ValueError, KeyError, AttributeError, TypeError, IndexError) as error:
        print(f"verify-boot: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
