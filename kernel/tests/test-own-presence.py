#!/usr/bin/env python3
"""Compile exact 0081/0082 helpers; optionally audit a pre-0082 patched XNU tree."""
import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / "kernel/patches/oneios-hosted"
PATCH = PATCHES / "0082-own-pmap-presence.patch"
PMAP = Path("osfmk/arm64/hosted/hosted_pmap.h")


def extract_header(patch, name):
    section = patch.read_text().split("+++ b/osfmk/arm64/hosted/" + name + "\n", 1)[1]
    section = section.split("\ndiff --git ", 1)[0]
    return "\n".join(line[1:] for line in section.splitlines() if line.startswith("+")) + "\n"


def audit(tree):
    subprocess.run([sys.executable, str(ROOT / "kernel/tests/test-fanout-presence.py"),
                    "--xnu-dir", str(tree)], check=True)
    old = (tree / PMAP).read_text()
    assert len(re.findall(r"\bhosted_task_unmap_locked\s*\(", old)) == 3, "unexpected unmap helper sites"
    assert "hosted_task_unmap_locked(pmap, va, end - va);" in old
    assert "hosted_task_unmap_locked(user, va, end - va);" in old
    subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=tree, check=True)
    # Inspect actual applied source, without touching the input tree.
    with tempfile.TemporaryDirectory(prefix="oneios-0082-audit-") as d:
        d = Path(d)
        (d / PMAP).parent.mkdir(parents=True)
        shutil.copyfile(tree / PMAP, d / PMAP)
        subprocess.run(["git", "apply", str(PATCH)], cwd=d, check=True)
        new = (d / PMAP).read_text()
        assert len(re.findall(r"\bhosted_task_unmap_locked\s*\(", new)) == 3
        assert "hosted_task_unmap_locked(pmap, va, end - va, true);" in new
        assert "hosted_task_unmap_locked(user, va, end - va, false);" in new
        assert 'hosted_own_presence, "oneios-own-presence", 0' in new
        assert "bzero(pmap->hosted_present_" not in new
        start = new.index("hosted_task_unmap_locked(pmap_t")
        end = new.index("\n}", start)
        body = new[start:end]
        assert body.count("HPC(task_unmap,") == 1
        assert body.index("if (!skip)") < body.index("HPC(task_unmap,") < body.index("hosted_check_unmapped(")
        assert "hosted_top_note_unmap(pmap)" in body
        assert "pmap->hosted_around" in body and "bzero(pmap->hosted_nested_seen" in body
    print("G22B_PATCHED_SOURCE_AUDIT=PASS input=pre0082 source_only=YES")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--xnu-dir", type=Path, help="actual XNU tree with 0081, without 0082")
    a = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="oneios-0082-model-") as d:
        d = Path(d)
        (d / "hosted_presence.h").write_text(extract_header(PATCHES / "0081-fanout-presence.patch", "hosted_presence.h"))
        (d / "hosted_own_presence.h").write_text(extract_header(PATCH, "hosted_own_presence.h"))
        subprocess.run(shlex.split(os.environ.get("CC", "cc")) +
                       ["-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-I", str(d),
                        str(ROOT / "kernel/tests/own-presence.c"), "-o", str(d / "test")], check=True)
        subprocess.run([str(d / "test")], check=True)
    if a.xnu_dir:
        audit(a.xnu_dir.resolve())
    else:
        print("G22B_PATCHED_SOURCE_AUDIT=NOT_RUN (pre-0082 XNU tree required)")


if __name__ == "__main__":
    main()
