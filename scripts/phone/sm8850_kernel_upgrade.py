"""Host-side, kernel-only SM8850 stage transaction. No guest launch or Data rearm."""
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import tarfile
import tempfile

NAMES = ("kernel.kc", "kernel.kc.hashes", "manifest.json")
SIDECARS = ("kernel.kc.gpuaddon", "kernel.kc.trustcache")
CACHE_SHA = "349c4692a6a85df0d396681f28d2d48dc04b95c6d60df0f94d84501e3d0c57e3"
CHUNK = 1 << 20
STAGE = "/data/adb/oneios-m3q-framework"
HEX = re.compile(r"[0-9a-f]{64}")
PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._/+-]*")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def obj(raw, name):
    value = json.loads(raw)
    require(isinstance(value, dict), f"{name}: expected object")
    return value


def valid_path(name):
    return (isinstance(name, str) and PATH.fullmatch(name) and
            ".." not in name and all(x not in ("", ".") for x in name.split("/")))


def table(raw, identity=False):
    pattern = re.compile(r"([0-9]+:[0-9]+:[0-9]+:[0-9]+)" if identity else HEX.pattern)
    result = {}
    for line in raw.decode("ascii").splitlines():
        parts = line.split()
        require(len(parts) == 2, "Malformed image stage metadata")
        value, name = parts
        require(pattern.fullmatch(value) and valid_path(name) and name not in result,
                f"Unsafe or repeated image stage entry: {name}")
        result[name] = value
    require(result, "Empty image stage metadata")
    return result


def validate_candidate(kernel, record_path, expected_new):
    require(isinstance(expected_new, str) and HEX.fullmatch(expected_new), "Invalid candidate SHA-256 pin")
    require(kernel.name == "kernel.kc" and kernel.is_file() and not kernel.is_symlink()
            and 32 <= kernel.stat().st_size <= 256 * CHUNK, "Invalid kernel collection path or size")
    hashes_path = kernel.with_name("kernel.kc.hashes")
    require(hashes_path.is_file() and not hashes_path.is_symlink(), "Missing independent chunk hash list")
    kc, chunks, record_raw = kernel.read_bytes(), hashes_path.read_bytes(), record_path.read_bytes()
    sha = digest(kc)
    require(sha == expected_new, "Candidate kernel SHA-256 mismatch")
    magic, cpu, subtype, filetype = struct.unpack_from("<IIII", kc)
    require(magic == 0xfeedfacf and cpu == 0x0100000c and subtype & 0x00ffffff == 2
            and filetype == 12, "Candidate is not an arm64e MH_FILESET")
    count = (len(kc) + CHUNK - 1) // CHUNK
    expected_chunks = struct.pack("<8sIIQQ", b"OIHL1\0\0\0", CHUNK, 1, len(kc), count)
    expected_chunks += b"".join(hashlib.sha256(kc[i:i+CHUNK]).digest()
                                for i in range(0, len(kc), CHUNK))
    require(chunks == expected_chunks, "Candidate chunk list differs from kernel")
    record = obj(record_raw, "kernel build record")
    require(record.get("output") == "kernel.kc" and record.get("format") == "MH_FILESET"
            and record.get("bytes") == len(kc) and record.get("sha256") == sha,
            "Kernel differs from independent prelink build record")
    inputs = record.get("inputs")
    require(isinstance(inputs, dict) and isinstance(inputs.get("kernelcache"), dict)
            and isinstance(inputs.get("kernel"), dict)
            and inputs["kernelcache"].get("sha256") == CACHE_SHA
            and isinstance(inputs["kernel"].get("sha256"), str)
            and HEX.fullmatch(inputs["kernel"]["sha256"]), "Build record is not pinned to 24A446")
    return {"kernel.kc": kc, "kernel.kc.hashes": chunks, "new-kernel-record.json": record_raw}


def make_payload(candidate, old_manifest, old_sha, old_ids, pins):
    sums = table(old_sha)
    ids = table(old_ids, identity=True)
    require(sums.keys() == ids.keys(), "Image hash and identity inventories differ")
    require(set(NAMES + SIDECARS) <= sums.keys(), "Missing staged kernel, manifest or sidecar")
    for name in ("kernel.kc", *SIDECARS):
        require(isinstance(pins.get(name), str) and HEX.fullmatch(pins[name])
                and sums[name] == pins[name], f"Unexpected installed pin: {name}")
    require(digest(candidate["kernel.kc"]) != sums["kernel.kc"], "Candidate already installed")
    require(digest(old_manifest) == sums["manifest.json"], "Installed manifest digest mismatch")
    manifest = obj(old_manifest, "image manifest")
    require(all(manifest.get(k) == v for k, v in {
        "format": 1, "name": "oneios-image", "version": "27.0.1", "build": "24A446",
        "device": "iPhone18,2", "arch": "arm64e", "kernel": "kernel.kc", "chunk": CHUNK,
    }.items()), "Unexpected image format, device or build")
    files = manifest.get("files")
    require(isinstance(files, list), "Missing image file inventory")
    entries = {}
    for entry in files:
        require(isinstance(entry, dict), "Invalid image manifest entry")
        name = entry.get("path")
        require(valid_path(name) and name not in entries and name != "manifest.json"
                and name in sums and entry.get("sha256") == sums[name]
                and type(entry.get("size")) is int and entry["size"] == int(ids[name].split(":")[2]),
                f"Manifest disagrees with stage inventory: {name}")
        entries[name] = entry
    require("kernel.kc" in entries and "kernel.kc.hashes" in entries, "Missing manifest kernel entries")
    kernel, hashes = entries["kernel.kc"], entries["kernel.kc.hashes"]
    require(kernel.get("role") == "kernel" and kernel.get("format") == "kernel-collection"
            and kernel.get("read_only") is True and kernel.get("hashes") == "kernel.kc.hashes"
            and hashes.get("role") == "hashes" and hashes.get("format") == "oneios-hash-list-1",
            "Unexpected kernel manifest schema")
    for name in NAMES[:2]:
        entries[name]["size"] = len(candidate[name])
        entries[name]["sha256"] = digest(candidate[name])
    new = {name: candidate[name] for name in NAMES[:2]}
    new["manifest.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    result = {"new/" + name: data for name, data in new.items()}
    result.update({
        "old.manifest.json": old_manifest,
        "old.image.sha256": old_sha,
        "old.image.ids": old_ids,
        "next.sha256": "".join(f"{digest(new[name])}  {name}\n" for name in NAMES).encode(),
        "new-kernel-record.json": candidate["new-kernel-record.json"],
    })
    return result


def upgrade_kernel(phone, candidate, pins, stager):
    def read(name):
        return phone.root(f"cat {STAGE}/{name}", binary=True, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, check=True, timeout=30).stdout

    payload = make_payload(candidate, read("image/manifest.json"),
                           read("image.sha256"), read("image.ids"), pins)
    payload["stage.sh"] = stager.read_bytes()
    # Check free space before accepting the tar, and again under the stage
    # lock in framework-stage.sh. The existing 30 GiB reserve is unchanged.
    reserve = 31457280 + 65536 + (sum(map(len, payload.values())) + 1048575) // 1024
    print("KERNEL_CANDIDATE_SHA256=" + digest(candidate["kernel.kc"]), flush=True)
    with tempfile.TemporaryFile() as packet:
        with tarfile.open(fileobj=packet, mode="w") as tar:
            for name, data in payload.items():
                entry = tarfile.TarInfo(name)
                entry.size, entry.mode = len(data), 0o600
                tar.addfile(entry, io.BytesIO(data))
        packet.seek(0)
        return phone.root(f"""set -eu
umask 077
[ "$(id -u)" = 0 ] && [ ! -L /data/adb ] && [ "$(stat -c '%u:%a' /data/adb)" = 0:700 ]
free=$(df -Pk /data/adb | awk 'NR==2 {{print $4}}')
[ "$free" -ge {reserve} ] || {{ echo 'STAGING REFUSED: insufficient kernel upload reserve' >&2; exit 2; }}
incoming=$(mktemp -d /data/adb/.oneios-m3q-upload.XXXXXX)
trap 'rm -rf "$incoming"' EXIT
tar -xf - -C "$incoming"
/system/bin/sh "$incoming/stage.sh" "$incoming" upgrade-kernel
""", stdin=packet, timeout=1200).returncode
