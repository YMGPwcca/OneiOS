#!/usr/bin/env python3
"""Read-only cross-layer GPU/respring forensics for a OneOS collection archive.

Evidence is correlated by monotonic timestamps within ONE session only. Events
that occur close in time are candidates, not proven causation. Never contacts ADB.
"""
import argparse
import json
import re
import tarfile
from pathlib import Path

STAMP = re.compile(r'^\[\s*([0-9]+(?:\.[0-9]+)?)\]')
GPU_ERROR = re.compile(r'GPU_COMMAND failed: (.*)')
BACKBOARD = re.compile(r'sheng-exit: backboardd\[(\d+)\] status (\S+)')
SPRINGBOARD = re.compile(r'sheng-exit: SpringBoard\[(\d+)\] status (\S+)')
FAULTS = re.compile(r'oneios-gpu-report:.*fence timeouts \+(\d+)')
TRAPS = re.compile(r'task traps \((\d+)/s\)')
HOST_GPU = re.compile(r'backboardd fences (\d+), submit->retired mean (\d+) us max (\d+) us')
DISP = re.compile(r'oneios-display: perf: mono_ms=(\d+) window_ms=(\d+) posts=(\d+) .*?gap_p95_us=(\d+) .*?copy_max_us=(\d+)')


def read_member(archive, name, max_size=48_000_000):
    try:
        m = archive.getmember(name)
    except KeyError:
        return None
    if not m.isfile() or m.size > max_size:
        raise ValueError(f'unsafe or oversized archive member: {name}')
    f = archive.extractfile(m)
    return f.read().decode('utf-8', 'replace') if f else None


def analyze(xnu, display=None, cap=None, thermal=None, outcome=None):
    events, gpu_errors, exits, samples, fence_timeouts, traps, display_windows = [], [], [], [], [], [], []
    for line in xnu.splitlines():
        mt = STAMP.match(line)
        if not mt:
            continue
        t = float(mt.group(1))
        err = GPU_ERROR.search(line)
        bb = BACKBOARD.search(line)
        sb = SPRINGBOARD.search(line)
        ft = FAULTS.search(line)
        tr = TRAPS.search(line)
        hp = HOST_GPU.search(line)
        if err:
            gpu_errors.append({'t': t, 'message': err.group(1), 'raw': line.strip()})
        if bb:
            exits.append({'t': t, 'process': 'backboardd', 'pid': int(bb.group(1)), 'status': bb.group(2)})
        if sb:
            exits.append({'t': t, 'process': 'SpringBoard', 'pid': int(sb.group(1)), 'status': sb.group(2),
                          'respawn': 'backboardd respawn' in line})
        if ft:
            fence_timeouts.append({'t': t, 'count_last_window': int(ft.group(1))})
        if tr:
            traps.append({'t': t, 'traps_per_s': int(tr.group(1))})
        if hp:
            samples.append({'t': t, 'fences': int(hp.group(1)), 'mean_us': int(hp.group(2)), 'max_us': int(hp.group(3))})
    if display:
        for line in display.splitlines():
            m = DISP.search(line)
            if m:
                t, window, posts, gap, copy = map(int, m.groups())
                display_windows.append({'t': t / 1000, 'window_ms': window, 'posts': posts,
                                        'gap_p95_ms': gap / 1000, 'copy_max_ms': copy / 1000})
    for error in gpu_errors:
        following = [e for e in exits if e['process'] == 'backboardd' and 0 <= e['t'] - error['t'] <= 30]
        if following:
            after = min(following, key=lambda e: e['t'])
            events.append({'gpu_error_t': error['t'], 'backboard_exit_t': after['t'],
                           'delta_seconds': round(after['t'] - error['t'], 3),
                           'interpretation': 'temporal association ONLY, not crash causality'})
    return {'provenance': 'READ_ONLY_SAME_SESSION_NOT_CAUSAL_PROOF',
            'gpu_command_errors': gpu_errors, 'guest_exits': exits,
            'gpu_error_to_backboard_exit': events, 'fence_timeout_samples': fence_timeouts,
            'host_gpu_fences': samples, 'traps': traps, 'display_windows': display_windows,
            'peak_traps_per_s': max((s['traps_per_s'] for s in traps), default=None),
            'max_host_submit_to_retire_ms': max((s['max_us'] / 1000 for s in samples), default=None),
            'max_display_gap_p95_ms': max((s['gap_p95_ms'] for s in display_windows), default=None),
            'max_display_copy_ms': max((s['copy_max_ms'] for s in display_windows), default=None),
            'cpu_cap_state': (cap or '').strip(), 'thermal_profile': (thermal or '').strip(),
            'return_outcome': (outcome or '').strip(),
            'qualification': 'NOT proof of FPS, independent watchdog safety, or root cause'}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', type=Path, required=True)
    ap.add_argument('--session', default='current', help='current or exact session suffix from logs/session.*')
    ap.add_argument('--output', type=Path)
    args = ap.parse_args(argv)
    if args.session != 'current' and not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', args.session):
        ap.error('invalid session suffix')
    prefix = '' if args.session == 'current' else f'logs/session.{args.session}/'
    with tarfile.open(args.archive, 'r:*') as archive:
        xnu = read_member(archive, prefix + 'session/xnuhost.log')
        if not xnu:
            ap.error('session/xnuhost.log missing or empty')
        results = analyze(xnu, read_member(archive, prefix + 'control/display.log'),
                          read_member(archive, prefix + 'control/cpu.best-effort.status'),
                          read_member(archive, prefix + 'control/framework.soft-thermal'),
                          read_member(archive, prefix + 'return.outcome'))
    results['session'] = args.session
    results['archive'] = str(args.archive)
    text = json.dumps(results, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
        print('GPU_RESPRING_REPORT=' + str(args.output))
    print('GPU_ERRORS=%d BACKBOARD_EXITS=%d SPRINGBOARD_EXITS=%d ASSOCIATIONS=%d PEAK_TRAPS_PER_S=%s MAX_HOST_GPU_FENCE_MS=%s MAX_DISPLAY_GAP_P95_MS=%s' % (
        len(results['gpu_command_errors']),
        sum(x['process'] == 'backboardd' for x in results['guest_exits']),
        sum(x['process'] == 'SpringBoard' for x in results['guest_exits']),
        len(results['gpu_error_to_backboard_exit']), results['peak_traps_per_s'],
        results['max_host_submit_to_retire_ms'], results['max_display_gap_p95_ms']))
    if not args.output:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
