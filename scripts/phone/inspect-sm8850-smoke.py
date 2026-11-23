#!/usr/bin/env python3
"""Read archived SM8850 takeover evidence without ADB or device mutations."""

import argparse
from pathlib import Path
import re
import sys
import tarfile


TEXT_LIMIT = 2_000_000


def text_file(path):
    if not path.is_file():
        return ""
    if path.stat().st_size > TEXT_LIMIT:
        return f"SKIPPED oversized file ({path.stat().st_size} bytes)"
    return path.read_text(encoding="utf-8", errors="replace")


def status_map(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def show_tail(title, body, limit=100):
    print(f"===== {title} =====")
    if not body:
        print("NOT_AVAILABLE")
        return
    lines = body.splitlines()
    if len(lines) > limit:
        print(f"... {len(lines) - limit} earlier lines omitted ...")
    print("\n".join(lines[-limit:]))


def inspect(folder):
    if not folder.is_dir():
        raise ValueError(f"Evidence directory missing: {folder}")
    print("EVIDENCE=" + str(folder))
    base = status_map(text_file(folder / "baseline.txt"))
    timeline = text_file(folder / "timeline.txt")
    boots = list(dict.fromkeys(re.findall(r"(?m)^boot=([^\r\n]+)", timeline)))
    states = list(dict.fromkeys(re.findall(r"(?m)^control/state=([^\r\n]+)", timeline)))
    print("BASE_BOOT=" + base.get("boot", "UNAVAILABLE"))
    print("OBSERVED_BOOTS=" + ", ".join(boots or ["UNAVAILABLE"]))
    print("OBSERVED_STATES=" + ", ".join(states or ["UNAVAILABLE"]))
    show_tail("TIMELINE FINAL", timeline, 70)
    archive = folder / "device-logs.tar"
    if not archive.is_file():
        print("ARCHIVE=NOT_AVAILABLE; the original session log may remain on the phone")
        return 2
    print("ARCHIVE=" + str(archive))
    wanted = (
        "return.log", "return.outcome", "control/state", "control/stopped",
        "control/framework.mode", "control/framework.return",
        "control/framework.launch", "control/framework.takeover-confirmed",
        "control/feeder.failed", "control/watchdog_feeder.log",
        "control/watchdog.phase", "control/return.step",
        "session/return.request",
    )
    found = {}
    with tarfile.open(archive, "r:*") as tar:
        for member in tar:
            name = member.name.removeprefix("./")
            if not member.isfile() or member.size > TEXT_LIMIT:
                continue
            if name not in wanted and not (name.startswith("launches/") and name.endswith("/switch.log")):
                continue
            entry = tar.extractfile(member)
            if entry is None:
                continue
            found[name] = entry.read().decode("utf-8", errors="replace")
    print("TAKEOVER_MARKER=" + ("PRESENT" if "control/framework.takeover-confirmed" in found else "ABSENT"))
    print("STOP_MARKER=" + ("PRESENT" if "control/stopped" in found else "ABSENT"))
    feeder = found.get("control/watchdog_feeder.log", "")
    if "Device or resource busy" in feeder and "OneOS legacy watchdog feeder" in found.get("control/feeder.failed", ""):
        print("LEGACY_WATCHDOG_HANDOFF=FAILED_EBUSY")
        print("EBUSY_OWNER=UNKNOWN_FROM_ARCHIVE")
    elif found.get("control/feeder.failed", "").strip():
        print("LEGACY_WATCHDOG_HANDOFF=FAILED_OTHER")
    else:
        print("LEGACY_WATCHDOG_HANDOFF=NOT_PROVEN")
    outcome = found.get("return.outcome", "").strip()
    print("RETURN_OUTCOME=" + (outcome or "UNAVAILABLE"))
    print("PHYSICAL_KEY_REBOOT=" + ("CANDIDATE_REQUIRES_NEW_BOOT_VERIFICATION"
                                 if outcome.startswith("reboot-key ") else "NOT_VERIFIED"))
    for name in wanted:
        if name in found:
            show_tail(name, found[name], 70 if name.endswith(".log") else 12)
    switch_logs = sorted(name for name in found if name.startswith("launches/") and name.endswith("/switch.log"))
    if not switch_logs:
        print("===== SWITCH LOG =====\nNOT_AVAILABLE")
    for name in switch_logs[-3:]:
        show_tail(name, found[name], 110)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="Existing out/sm8850/takeover/reboot-smoke-* directory")
    args = parser.parse_args()
    try:
        return inspect(args.evidence.resolve())
    except (OSError, ValueError, tarfile.TarError) as err:
        print(f"EVIDENCE_INSPECTION_FAILED: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
