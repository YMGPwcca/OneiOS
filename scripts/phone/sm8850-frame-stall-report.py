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

TS = re.compile(r'^\[\s*(\d+\.\d+)\]')
KVS = re.compile(r'([a-z][a-z0-9_]*)=([0-9.]+)')
CPU = re.compile(r'oneios-cpu: 10 s:.*\(all (\d+)%\)')
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
) -> tuple[str, str]:
    # Select a matched pair from ONE specific session. A current xnuhost
    # trace must never be joined with a historical display trace.
    prefix = f'logs/session.{archive_session}/' if archive_session else ''
    names = (prefix + 'session/xnuhost.log', prefix + 'control/display.log')
    if archive:
        with tarfile.open(archive, 'r:*') as tf:
            # A thermal abort can happen before xnuhost ever starts.
            # Missing guest traces are an expected, non-fatal outcome
            # of evidence collection and must not produce a traceback.
            members = {member.name: member for member in tf.getmembers()}
            missing = [name for name in names if name not in members]
            if missing:
                raise MissingTraceInputs(missing)
            parts = []
            for name in names:
                member = members[name]
                if not member.isfile() or member.size > MAX_BYTES:
                    raise ValueError(f'Invalid or oversized archive member: {name}')
                stream = tf.extractfile(member)
                if stream is None:
                    raise ValueError(f'Cannot read archive member: {name}')
                raw = stream.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError(f'Oversized archive member: {name}')
                parts.append(raw.decode('utf-8', 'replace'))
            return parts[0], parts[1]
    assert folder is not None
    missing = [name for name in names if not (folder / name).is_file()]
    if missing:
        raise MissingTraceInputs(missing)
    parts = []
    for name in names:
        path = folder / name
        if path.stat().st_size > MAX_BYTES:
            raise ValueError(f'Oversized file: {path}')
        parts.append(path.read_text(encoding='utf-8', errors='replace'))
    return parts[0], parts[1]


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
        display_events.append({'t': t, 'posts': int(data.get('posts', 0)),
                               'gap_p95_ms': data.get('gap_p95_us', 0) / 1000,
                               'copy_max_ms': data.get('copy_max_us', 0) / 1000,
                               'post_max_ms': data.get('post_max_us', 0) / 1000,
                               'window_ms': data.get('window_ms', 0)})
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
        if event['gap_p95_ms'] < 1000:
            continue
        t = event['t']
        touch = nearest(touch_events, t, 6)
        cpu = nearest(cpu_events, t, 16)
        traps = nearest(trap_events, t, 18)
        candidates.append({**event,
            'touch_nearby': touch,
            'cpu_nearby': cpu,
            'traps_nearby': traps,
            'interpretation': 'touch-linked candidate' if touch is not None else 'possibly idle; NOT a proven stall'})
    return {
        'provenance': 'READ_ONLY_CANDIDATES_NOT_CAUSAL_PROOF',
        'touch_summaries': len(touch_events),
        'touch_without_frame_before_summary_end': sum(x['no_frame_before_touch_summary_end'] for x in touch_events),
        'max_recorded_touch_to_guest_frame_ms': max((x['next_guest_frame_ms'] for x in touch_events
                                                     if x['next_guest_frame_ms'] is not None), default=None),
        'display_five_second_windows': len(display_events),
        'windows_with_post': sum(x['posts'] > 0 for x in display_events),
        'windows_without_post': sum(x['posts'] == 0 for x in display_events),
        'largest_active_gap_p95_ms': max((x['gap_p95_ms'] for x in display_events), default=0),
        'max_display_copy_ms': max((x['copy_max_ms'] for x in display_events), default=0),
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
    p.add_argument('--archive-session', metavar='TOKEN',
                   help='Use paired logs/session.TOKEN/{session/xnuhost.log,control/display.log} '
                        'from this archive, never mix sessions')
    p.add_argument('--list-sessions', action='store_true',
                   help='List archive sessions with paired xnuhost/display logs; no analysis')
    args = p.parse_args()
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
        data = analyze(*read_logs(args.archive, args.folder, args.archive_session),
                       thermal_csv=args.thermal_csv)
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
    print(f"FRAME_STALL_CANDIDATES={len(data['candidate_windows'])}; TOUCH_NO_FRAME={data['touch_without_frame_before_summary_end']}/{data['touch_summaries']}; MAX_DISPLAY_COPY_MS={data['max_display_copy_ms']:.2f}")
    for item in data['candidate_windows'][:20]:
        print(f"WINDOW_MONO={item['t']:.3f} gap_p95={item['gap_p95_ms']:.0f}ms posts={item['posts']} cpu={item['cpu_nearby']} traps={item['traps_nearby']} {item['interpretation']}")
    if args.output:
        print(f'REPORT={args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
