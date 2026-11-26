#!/usr/bin/env python3
"""Read-only correlation of guest frame gaps, touch summaries and xnuhost CPU/VM load.

Reports candidate windows, not proof of an input->pixel critical path.
Accepts an archived collect tarball OR an extracted session directory.
Never connects to the phone or changes device state.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import re
import tarfile
import sys
from sm8850_perf_metrics import active_post_summary, placement_evidence

TS = re.compile(r'^\[\s*(\d+\.\d+)\]')
KVS = re.compile(r'([a-z][a-z0-9_]*)=([0-9.]+)')
CPU = re.compile(r'(?:oneios-cpu|neios-cpu):\s*[0-9]+(?:\.[0-9]+)?\s*s:.*?\(all (\d+)%\)')
TRAPS = re.compile(r'xnuhost I perf: [\d.]+ s: (\d+) task traps \((\d+)/s\)')
TOUCH = re.compile(r'input: touch: .*?(no guest frame after the touch-down|the guest.s next frame ([\d.]+) ms after the touch-down)')
MAX_BYTES = 80 * 1024 * 1024


class MissingTraceInputs(Exception):
    """The archive is valid but cannot support a frame-stall analysis."""

    def __init__(self, paths: list[str]):
        self.paths = paths
        super().__init__(", ".join(paths))


def read_logs(
    archive: Path | None, folder: Path | None, archive_session: str | None = None,
    *, expected_launch: str | None = None, metadata: dict | None = None,
) -> tuple[str, str]:
    # Never join current and archived sessions, or silently substitute a stale
    # launch when the collector knows the requested launch identifier.
    prefix = f'logs/session.{archive_session}/' if archive_session else ''
    names = (prefix + 'session/xnuhost.log', prefix + 'control/display.log')
    controls = {key: prefix + 'control/' + file for key, file in (
        ('launch_id', 'framework.launch'), ('perf_profile', 'framework.perf-profile'),
        ('boot_id', 'boot'), ('mode', 'framework.mode'), ('cpu_profile', 'framework.cpu-profile'),
        ('interaction_profile', 'framework.interaction-profile'))}

    def finish(read):
        meta = {key: read(name, 256, optional=True) for key, name in controls.items()}
        meta = {key: value.strip() if value is not None else None for key, value in meta.items()}
        if expected_launch is not None and meta['launch_id'] != expected_launch:
            raise MissingTraceInputs(['launch metadata absent or mismatched'])
        if metadata is not None:
            metadata.update(meta)
        return tuple(read(name, MAX_BYTES) for name in names)

    if archive:
        with tarfile.open(archive, 'r:*') as tf:
            members = {}
            relevant = set(names) | set(controls.values())
            for member in tf.getmembers():
                if member.name not in relevant:
                    continue
                if member.name in members:
                    raise ValueError(f'Duplicate session member: {member.name}')
                members[member.name] = member

            def read(name, limit, optional=False):
                member = members.get(name)
                if member is None:
                    if optional:
                        return None
                    raise MissingTraceInputs([name])
                if not member.isfile() or member.size > limit:
                    raise ValueError(f'Invalid or oversized archive member: {name}')
                stream = tf.extractfile(member)
                if stream is None:
                    raise ValueError(f'Cannot read archive member: {name}')
                with stream:
                    raw = stream.read(limit + 1)
                if len(raw) > limit:
                    raise ValueError(f'Oversized archive member: {name}')
                return raw.decode('utf-8', 'replace')
            return finish(read)

    assert folder is not None
    def read(name, limit, optional=False):
        path = folder / name
        if not path.is_file():
            if optional:
                return None
            raise MissingTraceInputs([name])
        if path.stat().st_size > limit:
            raise ValueError(f'Oversized file: {path}')
        return path.read_text(encoding='utf-8', errors='replace')
    return finish(read)


def interaction_summary(host: str, metadata: dict) -> dict:
    """A valid receipt proves injection, not UI state or physical FPS."""
    rows = []
    for line in host.splitlines():
        if "SM8850_INTERACTION_V1 status=" not in line:
            continue
        payload = line.split("SM8850_INTERACTION_V1 ", 1)[1]
        rows.append(dict(re.findall(r"([a-z_]+)=([^\s]+)", payload)))
    profile = metadata.get("interaction_profile")
    begins = [r for r in rows if r.get("status") == "gesture_begin"]
    ends = [r for r in rows if r.get("status") == "gesture_end"]
    starts = [r for r in rows if r.get("status") == "start"]
    finishes = [r for r in rows if r.get("status") == "complete"]
    timeline = [r for r in rows if r.get("status") in ("start", "gesture_begin", "gesture_end", "complete")]
    valid = False
    if profile == "swipe-60s" and len(starts) == len(finishes) == 1 and len(begins) == len(ends) == 30:
        expected = ["start"] + [s for _ in range(30) for s in ("gesture_begin", "gesture_end")] + ["complete"]
        try:
            mono = [int(r["mono_ms"]) for r in timeline]
            valid = ([r["status"] for r in timeline] == expected and mono == sorted(mono) and
                     [int(r["index"]) for r in begins] == list(range(1, 31)) and
                     [int(r["index"]) for r in ends] == list(range(1, 31)) and
                     starts[0].get("profile") == profile and starts[0].get("planned") == "30" and
                     finishes[0].get("completed") == "30" and
                     60000 <= int(finishes[0]["elapsed_ms"]) <= 65000 and
                     int(starts[0]["deadline_ms"]) - int(starts[0]["boot_ms"]) >= 75000 and
                     not any(r.get("status") in ("aborted", "skipped", "refused") for r in rows))
        except (KeyError, ValueError):
            pass
    return {"profile": profile, "status": "COMPLETE" if valid else
            ("OFF" if profile in (None, "off") and not rows else "INCOMPLETE_OR_MISMATCH"),
            "gesture_begins": len(begins), "gesture_ends": len(ends),
            "start_mono_ms": int(starts[0]["mono_ms"]) if valid else None,
            "end_mono_ms": int(finishes[0]["mono_ms"]) if valid else None,
            "elapsed_ms": int(finishes[0]["elapsed_ms"]) if valid else None,
            "events": rows, "scope": "injected gesture receipt only; UI state and physical presentation unverified"}


def interaction_display_summary(display: str, receipt: dict) -> dict:
    """Use only whole display windows within a verified interaction interval."""
    if receipt["status"] != "COMPLETE":
        return {"status": "UNAVAILABLE_INCOMPLETE_INTERACTION", "active_post_summary": None}
    selected = []
    for line in display.splitlines():
        if "oneios-display: perf:" not in line:
            continue
        values = {k: float(v) if "." in v else int(v) for k, v in KVS.findall(line)}
        end = values.get("mono_ms")
        duration = values.get("window_ms")
        if (end is not None and duration is not None and duration > 0 and
                end - duration >= receipt["start_mono_ms"] and end <= receipt["end_mono_ms"]):
            selected.append(values)
    return {"status": "MEASURED_NOT_PHYSICAL_FPS" if selected else "NO_WHOLE_WINDOWS",
            "whole_windows": len(selected), "active_post_summary": active_post_summary(selected),
            "peak_post_rate": max((1000 * r["posts"] / r["window_ms"] for r in selected
                                   if "posts" in r), default=None)}


def nearest(events, at, max_diff):
    return min((ev for ev in events if abs(ev['t'] - at) <= max_diff),
               key=lambda ev: abs(ev['t'] - at), default=None)


def analyze(xnu: str, display: str, thermal_csv: Path | None = None) -> dict:
    cpu_events, trap_events, touch_events = [], [], []
    for line in xnu.splitlines():
        m = TS.match(line)
        if not m:
            continue
        t = float(m.group(1))
        if match := CPU.search(line):
            cpu_events.append({'t': t, 'guest_cpu_pct': int(match.group(1))})
        if match := TRAPS.search(line):
            trap_events.append({'t': t, 'traps_per_s': int(match.group(2)),
                                'traps_in_window': int(match.group(1))})
        if match := TOUCH.search(line):
            delay = float(match.group(2)) if match.group(2) else None
            touch_events.append({'t': t, 'no_frame_before_touch_summary_end': delay is None,
                                 'next_guest_frame_ms': delay})
    display_events = []
    for line in display.splitlines():
        if 'oneios-display: perf:' not in line:
            continue
        data = {key: float(val) if '.' in val else int(val)
                for key, val in KVS.findall(line)}
        if 'mono_ms' not in data:
            continue
        t = data['mono_ms'] / 1000
        def ms(key):
            return data[key] / 1000 if key in data else None
        active_fields = {key: data[key] for key in
                         ('active_gaps', 'active_gap_p95_us', 'active_gap_p99_us',
                          'active_gap_max_us', 'active_over_60', 'active_over_120')
                         if key in data}
        display_events.append({'t': t, 'posts': data.get('posts'),
                               'gap_p95_ms': ms('gap_p95_us'),
                               'copy_max_ms': ms('copy_max_us'),
                               'post_max_ms': ms('post_max_us'),
                               'window_ms': data.get('window_ms'), **active_fields})
    thermal_events = []
    if thermal_csv:
        with thermal_csv.open(newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                try:
                    elapsed = float(row['elapsed_s'])
                    temp = float(row['cpu_max_c'])
                except (KeyError, ValueError):
                    continue
                # Thermal CSV is relative to Framework stop, while log t
                # is boot monotonic. Do not invent a clock shift to join them.
                thermal_events.append({'elapsed_from_framework_stop_s': elapsed,
                                       'cpu_max_c': temp})
    candidates = []
    for event in display_events:
        if event['gap_p95_ms'] is None or event['gap_p95_ms'] < 1000:
            continue
        t = event['t']
        touch = nearest(touch_events, t, 6)
        cpu = nearest(cpu_events, t, 16)
        traps = nearest(trap_events, t, 18)
        candidates.append({**event,
            'touch_nearby': touch,
            'cpu_nearby': cpu,
            'traps_nearby': traps,
            'interpretation': 'all-gap candidate near touch; may include idle; NOT a proven stall' if touch is not None else 'possibly idle; NOT a proven stall'})
    summary = active_post_summary(display_events)
    active_p95 = summary['max_window_active_p95_bucket_bound_us']
    return {
        'provenance': 'READ_ONLY_CANDIDATES_NOT_CAUSAL_PROOF',
        'touch_summaries': len(touch_events),
        'touch_without_frame_before_summary_end': sum(x['no_frame_before_touch_summary_end'] for x in touch_events),
        'max_recorded_touch_to_guest_frame_ms': max((x['next_guest_frame_ms'] for x in touch_events
                                                     if x['next_guest_frame_ms'] is not None), default=None),
        'display_five_second_windows': len(display_events),
        'windows_with_post': sum(x['posts'] is not None and x['posts'] > 0 for x in display_events),
        'windows_without_post': sum(x['posts'] == 0 for x in display_events),
        'windows_missing_post_count': sum(x['posts'] is None for x in display_events),
        'largest_active_gap_p95_ms': active_p95 / 1000 if active_p95 is not None else None,
        'largest_all_gap_p95_bucket_bound_ms': max((x['gap_p95_ms'] for x in display_events
                                                   if x['gap_p95_ms'] is not None and x['gap_p95_ms'] > 0), default=None),
        'active_post_summary': summary,
        'cpu_placement': placement_evidence(xnu),
        'candidate_windows_scope': 'all-gap p95 bucket bound >= 1000ms; may include idle',
        'max_display_copy_ms': max((x['copy_max_ms'] for x in display_events
                                    if x['copy_max_ms'] is not None and x['posts'] is not None and x['posts'] > 0), default=None),
        'peak_guest_cpu_pct_window': max((x['guest_cpu_pct'] for x in cpu_events), default=None),
        'peak_traps_per_s_window': max((x['traps_per_s'] for x in trap_events), default=None),
        'candidate_windows': candidates,
        'separate_thermal_samples_no_clock_alignment': thermal_events,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument('--archive', type=Path)
    src.add_argument('--folder', type=Path)
    p.add_argument('--thermal-csv', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--expected-launch', help='Reject a paired session whose control/framework.launch differs')
    p.add_argument('--archive-session', metavar='TOKEN',
                   help='Use paired logs/session.TOKEN/{session/xnuhost.log,control/display.log} '
                        'from this archive, never mix sessions')
    p.add_argument('--list-sessions', action='store_true',
                   help='List archive sessions with paired xnuhost/display logs; no analysis')
    args = p.parse_args()
    if args.expected_launch and not re.fullmatch(r'[a-f0-9]{32}', args.expected_launch):
        p.error('invalid --expected-launch identifier')
    if args.archive_session and not args.archive:
        p.error('--archive-session requires --archive')
    if args.archive_session and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.archive_session):
        p.error('invalid --archive-session token')
    if args.list_sessions:
        if not args.archive:
            p.error('--list-sessions requires --archive')
        try:
            with tarfile.open(args.archive, 'r:*') as tf:
                names = {m.name for m in tf.getmembers() if m.isfile()}
            tokens = sorted(set(
                re.fullmatch(r'logs/session\.([A-Za-z0-9_-]+)/session/xnuhost\.log', name).group(1)
                for name in names
                if re.fullmatch(r'logs/session\.([A-Za-z0-9_-]+)/session/xnuhost\.log', name)
            ))
            print('FRAME_STALL_SESSION=current '
                  f'xnu={int("session/xnuhost.log" in names)} '
                  f'display={int("control/display.log" in names)}')
            for token in tokens:
                base = f'logs/session.{token}/'
                print(f'FRAME_STALL_SESSION={token} xnu=1 '
                      f'display={int(base + "control/display.log" in names)}')
            return 0
        except (OSError, ValueError, tarfile.TarError) as error:
            print(f'FRAME_STALL_REPORT=ERROR {type(error).__name__}: {error}',
                  file=sys.stderr)
            return 2
    try:
        metadata = {}
        xnu, display = read_logs(args.archive, args.folder, args.archive_session,
                                 expected_launch=args.expected_launch, metadata=metadata)
        data = analyze(xnu, display, thermal_csv=args.thermal_csv)
        data['session_metadata'] = metadata
        data['interaction'] = interaction_summary(xnu, metadata)
        data['interaction_display'] = interaction_display_summary(display, data['interaction'])
        data['runtime_trace_observed'] = {
            'runtime_profile_markers': re.findall(r'(?m)^ONEIOS_PERF_PROFILE=(off|frame|task|frame-task)$', xnu),
            'queue_lines': xnu.count('gpu-queue-trace:'),
            'fence_lines': xnu.count('gpu-fence-trace:'),
            'task_profile_lines': xnu.count('perf-task:'),
            'transport_lines': display.count('oneios-display: frame-trace:'),
            'scanout_lines': display.count('oneios-display: scanout-trace:'),
        }
        data['expected_launch_matched'] = True if args.expected_launch else None
        data['source_session'] = (f'logs/session.{args.archive_session}'
                                  if args.archive_session else 'current')
        data['source_pairing'] = 'SAME_SESSION_ONLY_NOT_CROSS_BOOT_PROOF'
    except MissingTraceInputs as error:
        print('FRAME_STALL_REPORT=SKIPPED_MISSING_GUEST_TRACE '
              f'missing={",".join(error.paths)}', file=sys.stderr)
        return 3
    except (OSError, ValueError, tarfile.TarError, KeyError) as error:
        print(f'FRAME_STALL_REPORT=ERROR {type(error).__name__}: {error}',
              file=sys.stderr)
        return 2
    result = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding='utf-8')
    copy_max = data['max_display_copy_ms']
    receipt = data['interaction']
    print(f"INTERACTION_RECEIPT={receipt['status']} profile={receipt['profile']} begins={receipt['gesture_begins']} ends={receipt['gesture_ends']}")
    if receipt["status"] == "COMPLETE":
        print("INTERACTION_DISPLAY=" + json.dumps(data["interaction_display"], sort_keys=True))
    print(f"FRAME_STALL_CANDIDATES={len(data['candidate_windows'])}; TOUCH_NO_FRAME={data['touch_without_frame_before_summary_end']}/{data['touch_summaries']}; MAX_DISPLAY_COPY_MS=" +
          (f"{copy_max:.2f}" if copy_max is not None else "UNKNOWN"))
    for item in data['candidate_windows'][:20]:
        print(f"WINDOW_MONO={item['t']:.3f} gap_p95={item['gap_p95_ms']:.0f}ms posts={item['posts']} cpu={item['cpu_nearby']} traps={item['traps_nearby']} {item['interpretation']}")
    if args.output:
        print(f'REPORT={args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
