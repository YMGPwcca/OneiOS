#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the synthetic ram=auto fixture, including a finite mlock budget."""
import argparse
from pathlib import Path
import re


HOST = r"^\[[^\]\n]+\] xnuhost I "
GUEST = r"^\[[^\]\n]+\] guest +"


def one(log: str, pattern: str) -> re.Match:
    matches = list(re.finditer(HOST + pattern, log, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError(f"expected one {pattern!r} record, got {len(matches)}")
    return matches[0]


def validate(log: str) -> tuple[str, int, int]:
    size = int(one(log, r"memory: ram=auto: host MemTotal 4096 MiB, MemAvailable 2560 MiB; "
                        r"the guest gets (1024|1280) MiB: .+$")[1])
    start = one(log, r"memory: the guest's RAM is held for the session: (\d+) MiB, "
                     r"prefaulted on a thread at nice 19 in (\d+) MiB steps, locked as it goes \(mlock\)"
                     r"[^\n]*; free pages are not given back \(ram-giveback=0\); .+$")
    if int(start[1]) != size or int(start[2]) <= 0:
        raise ValueError("fixed RAM size or step does not match the auto fixture")
    step = int(start[2])
    done = one(log, r"memory: the guest's RAM is held: (\d+) MiB prefaulted in \d+ ms, (.+)$")
    prefaulted, why = int(done[1]), done[2]
    partial = re.fullmatch(r"(\d+) MiB of it locked \(mlock: [^\n]+ past that; what is locked stays locked\), "
                           r"not prefaulted further: the rest is faulted in as iOS uses it", why)
    if why == "locked (mlock: the host cannot swap it)" and prefaulted == size:
        mode = "full"
    elif (partial and 0 < prefaulted < size and prefaulted == int(partial[1])
          and prefaulted % step == 0):
        mode = "partial"
    elif prefaulted == 0 and re.fullmatch(
            r"not locked \(mlock: [^\n]+\), so not prefaulted: the guest's RAM is faulted in as iOS uses it "
            r"\(an unlocked, unused page is the first the host swaps\)", why):
        mode = "none"
    else:
        raise ValueError(f"inconsistent prefault/lock result: {prefaulted} MiB, {why}")
    # The fixture uses constant MemAvailable above the valve threshold; the
    # successfully locked prefix must remain locked until the end of the run.
    end = one(log, r"memory: the guest's RAM: (\d+) MiB held to the end, (\d+) MiB of it locked; "
                   r"the exit gives all of it back to the host$")
    if (int(end[1]), int(end[2])) != (size, prefaulted):
        raise ValueError("final held/locked RAM disagrees with the completed prefault")
    if not (start.start() < done.start() < end.start()):
        raise ValueError("RAM lifecycle records are out of order")
    if not re.search(GUEST + r"TESTKERNEL: all passed$", log, re.MULTILINE):
        raise ValueError("synthetic guest did not finish successfully")
    if re.search(GUEST + r"TESTKERNEL: FAIL", log, re.MULTILINE):
        raise ValueError("synthetic guest reported a failure")
    one(log, r"exit 0$")
    return mode, size, prefaulted


def self_test() -> None:
    def fixture(size: int, n: int, why: str, final_locked: int | None = None) -> str:
        return (f"[  1.000] xnuhost I memory: ram=auto: host MemTotal 4096 MiB, MemAvailable 2560 MiB; the guest gets {size} MiB: what fits\n"
                f"[  1.001] xnuhost I memory: the guest's RAM is held for the session: {size} MiB, prefaulted on a thread at nice 19 in 16 MiB steps, locked as it goes (mlock) (the valve: test); free pages are not given back (ram-giveback=0); test facts\n"
                f"[  1.002] xnuhost I memory: the guest's RAM is held: {n} MiB prefaulted in 10 ms, {why}\n"
                "[  1.003] guest     TESTKERNEL: all passed\n"
                f"[  1.004] xnuhost I memory: the guest's RAM: {size} MiB held to the end, {n if final_locked is None else final_locked} MiB of it locked; the exit gives all of it back to the host\n"
                "[  1.005] xnuhost I exit 0\n")

    full = "locked (mlock: the host cannot swap it)"
    partial = ("64 MiB of it locked (mlock: Cannot allocate memory past that; what is locked stays locked), "
               "not prefaulted further: the rest is faulted in as iOS uses it")
    none = ("not locked (mlock: Operation not permitted), so not prefaulted: the guest's RAM is faulted in as iOS uses it "
            "(an unlocked, unused page is the first the host swaps)")
    valid = fixture(1024, 64, partial)
    assert validate(fixture(1280, 1280, full)) == ("full", 1280, 1280)
    assert validate(valid) == ("partial", 1024, 64)
    assert validate(fixture(1024, 0, none)) == ("none", 1024, 0)
    invalid = [fixture(1024, 64, full), fixture(1024, 32, partial),
               fixture(1024, 65, partial.replace("64 MiB", "65 MiB")),
               fixture(1024, 64, partial, 0), fixture(1024, 64, none),
               fixture(2048, 64, partial), valid.replace("ram-giveback=0", "ram-giveback=1"),
               valid.replace("TESTKERNEL: all passed", "TESTKERNEL: FAIL"),
               valid.replace("exit 0", "exit 3"), valid.replace("not prefaulted further", "prefaulted further"),
               valid.replace("64 MiB prefaulted in 10 ms, " + partial, "64 MiB prefaulted in 10 ms, " + full),
               valid.replace("; the exit gives all of it back to the host", ""),
               valid + valid]
    for i, log in enumerate(invalid):
        try:
            validate(log)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid fixture {i}")
    print(f"RAM_AUTO_LOG_SELF_TEST=PASS cases={3 + len(invalid)}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("log", nargs="?", type=Path)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        self_test()
        return 0
    if a.log is None:
        p.error("log path required")
    try:
        mode, size, locked = validate(a.log.read_text(errors="replace"))
    except (OSError, ValueError) as e:
        print(f"RAM_AUTO_LOG=FAIL {e}")
        return 1
    print(f"RAM_AUTO_LOG=PASS mode={mode} size_mib={size} locked_mib={locked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
