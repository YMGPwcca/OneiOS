#!/usr/bin/env python3
"""Compile the actual 0081 helper, and optionally audit the patched XNU map sites."""
import argparse
import pathlib
import re
import shlex
import os
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATCH = ROOT / "kernel/patches/oneios-hosted/0081-fanout-presence.patch"
NAME = "osfmk/arm64/hosted/hosted_presence.h"

def audit_tree(root):
    sources = [p for p in (root / "osfmk").rglob("*") if p.suffix in (".c", ".h", ".cpp") and p.is_file()]
    sites = []
    for path in sources:
        s = path.read_text(errors="replace")
        for m in re.finditer(r"\bHPC\s*\(\s*task_map\s*,", s):
            assert path == root / "osfmk/arm64/hosted/hosted_pmap.h", (path, m.start())
            assert "hosted_nested_mark(pmap," in s[max(0,m.start()-200):m.start()], (path,m.start())
            sites.append((path,m.start()))
    assert len(sites) == 2, f"unexpected map publication sites: {sites}"
    pmap = (root / "osfmk/arm64/hosted/hosted_pmap.h").read_text()
    assert "hosted_presence_mark(pmap->hosted_present_tags" in pmap
    assert "hosted_presence_forget(" not in pmap
    assert "bzero(pmap->hosted_present_" not in pmap
    assert "hosted_presence_maybe(user->hosted_present_tags" in pmap
    print("G2_PATCHED_XNU_MAP_SITES=PASS (normal and fault-around)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xnu-dir", type=pathlib.Path, help="actual patched XNU source root, not pristine pin")
    args = ap.parse_args()
    text = PATCH.read_text()
    section = text.split("+++ b/" + NAME + "\n", 1)[1].split("\ndiff --git ",1)[0]
    lines = section.splitlines()
    header = "\n".join(line[1:] for line in lines if line.startswith("+")) + "\n"
    assert "hosted_presence_mark" in header and "hosted_presence_maybe" in header
    assert "hosted_presence_forget" not in header
    with tempfile.TemporaryDirectory(prefix="oneios-g2-presence-") as folder:
        folder = pathlib.Path(folder)
        (folder / "hosted_presence.h").write_text(header)
        subprocess.run(shlex.split(os.environ.get("CC", "cc")) +
                       ["-std=c11","-Wall","-Wextra","-Werror","-O2","-I",str(folder),
                        str(ROOT/"kernel/tests/fanout-presence.c"),"-o",str(folder/"test")],check=True)
        subprocess.run([str(folder/"test")],check=True)
    if args.xnu_dir:
        audit_tree(args.xnu_dir.resolve())

if __name__ == "__main__":
    main()
