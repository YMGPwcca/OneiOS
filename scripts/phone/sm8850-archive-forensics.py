#!/usr/bin/env python3
"""Read-only SM8850 post-run thermal and recovery evidence inventory.

Reads an already collected device-logs.tar without extracting any member,
connecting to ADB, opening watchdog devices or modifying APFS Data.
Archived sessions and the current control directory are kept separate.
Append-only thermal logs are not attributed to a session without a matching
boot ID and generation in their individual records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

MAX_FIELD_BYTES = 16 * 1024
MAX_LOG_BYTES = 4 * 1024 * 1024
SESSION_PATTERN = re.compile(r"^logs/(session\.[A-Za-z0-9_-]{1,64})/")
FIELDS = (
    "control/boot",
    "control/state",
    "control/framework.mode",
    "control/framework.return",
    "control/framework.deadline",
    "control/framework.launch",
    "control/watchdog.generation",
    "control/watchdog.phase",
    "control/watchdog.target",
    "control/watchdog.owner",
    "control/thermal.guard.required",
    "control/thermal.guard.heartbeat",
    "control/thermal.guard.fault",
    "control/thermal.cap.required",
    "control/thermal.cap.heartbeat",
    "control/thermal.cap.fault",
    "return.outcome",
    "session/return.request",
)
LOG_FIELDS = ("return.log", "control/watchdog_feeder.log")
KEYWORDS = re.compile(
    r"fault|abort|fail|reboot|return|deadline|timeout|watchdog|"
    r"thermal|P0_CPU_CAP|unachievable|min_floor|generation|boot",
    re.IGNORECASE,
)


def get_text(tf: tarfile.TarFile, members: dict, name: str,
             limit: int = MAX_FIELD_BYTES) -> str | None:
    entry = members.get(name)
    if entry is None:
        return None
    if not entry.isfile():
        return "<NON_REGULAR_ARCHIVE_MEMBER>"
    if entry.size > limit:
        return f"<OVERSIZED_MEMBER size={entry.size} limit={limit}>"
    stream = tf.extractfile(entry)
    if stream is None:
        return "<UNREADABLE_ARCHIVE_MEMBER>"
    data = stream.read(limit + 1)
    if len(data) > limit:
        return "<MEMBER_EXCEEDS_LIMIT>"
    return data.decode("utf-8", "replace").strip()


def selected_tail(text: str | None, count: int = 18) -> list[str]:
    if text is None:
        return []
    lines = text.splitlines()
    matched = [line[:320] for line in lines if KEYWORDS.search(line)]
    return (matched or [line[:320] for line in lines])[-count:]


def session_report(tf: tarfile.TarFile, members: dict, prefix: str) -> dict:
    result = {
        "session": prefix.rstrip("/") or "CURRENT",
        "fields": {},
        "logs": {},
        "guest_trace_present": (prefix + "session/xnuhost.log") in members,
        "display_trace_present": (prefix + "control/display.log") in members,
    }
    for name in FIELDS:
        value = get_text(tf, members, prefix + name)
        if value is not None:
            result["fields"][name] = value
    for name in LOG_FIELDS:
        value = get_text(tf, members, prefix + name, MAX_LOG_BYTES)
        if value is not None:
            result["logs"][name] = selected_tail(value)
    return result


def collect_report(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    with tarfile.open(path, mode="r:*") as tf:
        entries = tf.getmembers()
        members = {}
        duplicates = []
        for member in entries:
            if member.name in members:
                duplicates.append(member.name)
            else:
                members[member.name] = member
        if duplicates:
            raise ValueError(f"Ambiguous duplicate TAR members: {duplicates[:5]!r}")
        historic = sorted({
            match.group(1) for name in members
            if (match := SESSION_PATTERN.match(name))
        })
        report = {
            "scope": "ARCHIVE_ONLY_NO_ADB_NO_REARM_NO_TAKEOVER",
            "provenance": "SESSION_FILES_ARE_SEPARATE; APPEND_ONLY_LOGS_UNATTRIBUTED",
            "archive_sha256": digest.hexdigest(),
            "archive_size_bytes": path.stat().st_size,
            "current": session_report(tf, members, ""),
            "archived_sessions": [
                session_report(tf, members, f"logs/{token}/")
                for token in historic
            ],
            "append_only_unattributed": {},
        }
        for name in ("thermal-guard.log", "thermal-cap.log"):
            raw = get_text(tf, members, name, MAX_LOG_BYTES)
            if raw is not None:
                report["append_only_unattributed"][name] = {
                    "note": "Do not attribute to a boot/session without log-level provenance",
                    "matching_tail": selected_tail(raw, count=40),
                }
        return report


def brief(report: dict) -> None:
    print("SM8850_ARCHIVE_FORENSICS=READ_ONLY")
    print(f"ARCHIVE_SHA256={report['archive_sha256']}")
    for item in [report["current"], *report["archived_sessions"]]:
        fields = item["fields"]
        print(f"SESSION={item['session']} "
              f"boot={fields.get('control/boot', 'UNKNOWN')[:90]} "
              f"generation={fields.get('control/watchdog.generation', 'UNKNOWN')[:90]} "
              f"guest_trace={int(item['guest_trace_present'])} "
              f"display_trace={int(item['display_trace_present'])}")
        for name in ("control/thermal.guard.fault", "control/thermal.cap.fault",
                     "return.outcome"):
            if name in fields:
                print(f"  {name}={fields[name][:360]!r}")
    for name, data in report["append_only_unattributed"].items():
        print(f"APPEND_ONLY={name} matching_tail={len(data['matching_tail'])} "
              "SESSION_ATTRIBUTION=UNVERIFIED")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = collect_report(args.archive)
        brief(report)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"P0_EVIDENCE_JSON={args.output}")
        return 0
    except (OSError, ValueError, tarfile.TarError) as error:
        print(f"SM8850_ARCHIVE_FORENSICS=ERROR {type(error).__name__}: {error}",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
