"""Read-only performance telemetry helpers. Counts describe posted buffers, not panel presentation."""
import re

CPU_HEADER = re.compile(r"(?:oneios-cpu|neios-cpu)(?:-[A-Za-z0-9_-]+)?:\s*([0-9]+(?:\.[0-9]+)?)\s*s:\s*")
MONO_PREFIX = re.compile(r"\[\s*\d+\.\d+\]")


def cpu_payloads(text):
    """Recognize exact top-process sampler markers even when logs are glued.
    Exclude the distinct -sys sampler and stop at the next marker/timestamp.
    """
    for line in text.splitlines():
        matches = list(CPU_HEADER.finditer(line))
        for i, match in enumerate(matches):
            header = match.group()
            if not re.match(r"(?:oneios-cpu|neios-cpu):", header):
                continue
            if float(match.group(1)) <= 0:
                continue
            payload = line[match.end():matches[i+1].start() if i+1 < len(matches) else len(line)]
            boundary = MONO_PREFIX.search(payload)
            if boundary:
                payload = payload[:boundary.start()]
            yield payload


def process_cpu_samples(text, name):
    pattern = re.compile(r"(?<![\w-])" + re.escape(name) + r"\[\d+\]\s+(\d+)%")
    return [max(values) for payload in cpu_payloads(text)
            if (values := [int(value) for value in pattern.findall(payload)])]


def active_post_summary(rows):
    """Never fill missing telemetry with zero or pool histogram quantiles."""
    def count(row, key):
        value = row.get(key)
        return value if type(value) is int and value >= 0 else None

    observed = [r for r in rows if count(r, "active_gaps") is not None]
    budget = [r for r in observed
              if all(count(r, key) is not None for key in ("active_over_60", "active_over_120"))
              and 0 <= r["active_over_60"] <= r["active_over_120"] <= r["active_gaps"]]
    measured = [r for r in observed if r["active_gaps"] > 0]
    def total(items, key):
        return sum(r[key] for r in items) if items else None
    def peak(key):
        return max((r[key] for r in measured if count(r, key) is not None), default=None)
    denominator = total(budget, "active_gaps")
    over60 = total(budget, "active_over_60")
    over120 = total(budget, "active_over_120")
    return {
        "scope": "active adjacent Android post gaps; not dropped frames or physical FPS",
        "display_windows": len(rows),
        "active_count_windows": len(observed),
        "budget_count_windows": len(budget),
        "budget_coverage_complete": bool(rows) and len(budget) == len(rows),
        "active_gaps_reported": total(observed, "active_gaps"),
        "active_gaps_with_budget_counts": denominator,
        "over_60_budget": over60,
        "over_120_budget": over120,
        "over_60_budget_percent": 100 * over60 / denominator if denominator else None,
        "over_120_budget_percent": 100 * over120 / denominator if denominator else None,
        "max_window_active_p95_bucket_bound_us": peak("active_gap_p95_us"),
        "max_window_active_p99_bucket_bound_us": peak("active_gap_p99_us"),
        "max_active_gap_us": peak("active_gap_max_us"),
    }

def placement_evidence(host):
    """Separate requested topology, sampled effective masks and placement
    call outcomes. Never sum cumulative counters or infer CPU residency."""
    plans, targets, affinities, outcomes, profiles = [], [], [], [], []
    for line in host.splitlines():
        if m := re.search(r"SM8850_CPU_PROFILE=(PRIME_FIRST_ACTIVE|DEFAULT_FALLBACK|DEFAULT)\b", line):
            profiles.append(m.group(1))
        if m := re.search(r"cpu: vCPU (\d+) \(([EP])\) is described to iOS as host CPU (\d+): (\d+)-(\d+) kHz, (\d+) table entries, capacity (\d+)", line):
            vcpu, cluster, cpu, low, high, nfreq, capacity = m.groups()
            plans.append(dict(vcpu=int(vcpu), cluster=cluster, host_cpu=int(cpu),
                              min_khz=int(low), max_khz=int(high),
                              nfreq=int(nfreq), capacity=int(capacity)))
        if m := re.search(r"cpu(\d+): host CPU mask (0x[0-9a-fA-F]+)", line):
            targets.append(dict(vcpu=int(m.group(1)), target_mask=m.group(2)))
        if m := re.search(r"perf-affinity: vcpu=(\d+) tid=(\d+) allowed=(\S+) migrations=(\S+) last_cpu=(-?\d+)", line):
            vcpu, tid, allowed, migrations, last_cpu = m.groups()
            affinities.append(dict(vcpu=int(vcpu), tid=int(tid),
                                  allowed=None if allowed == "unknown" else allowed,
                                  migrations=int(migrations) if migrations.isdecimal() else None,
                                  last_cpu=int(last_cpu) if int(last_cpu) >= 0 else None))
        if m := re.search(r"perf-placement: vcpu=(\d+) role=(vcpu|guest-thread|service-thread) calls=(\d+) failed=(\d+) readback_samples=(\d+) readback_errors=(\d+) readback_mismatches=(\d+) current_target=(0x[0-9a-fA-F]+)", line):
            vcpu, role, calls, failed, samples, errors, mismatches, target = m.groups()
            outcomes.append(dict(vcpu=int(vcpu), role=role, calls=int(calls), failed=int(failed),
                                 readback_samples=int(samples), readback_errors=int(errors),
                                 readback_mismatches=int(mismatches), current_target=target))
    return {
        "runtime_profile_markers": profiles,
        "described_cores": plans,
        "initial_target_masks": targets,
        "vcpu_affinity_samples": affinities,
        "placement_cumulative_samples": outcomes,
        "residency": None,
        "scope": "target masks are not effective affinity; sampled readback is not CPU residency or proof of GPU/display worker contention",
    }
