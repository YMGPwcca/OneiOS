# Phase 3 SM8850 recovery dry-run

**OneiOS · Galaxy S26 Ultra / SM8850 · Recovery drill-down**

[← Handbook](README.md) · [Current status](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md)

> [!NOTE]
> **Historical source or earlier experimental procedure.** The latest S26 Ultra full guest ran ~600.6 s with a displayed frame, but serious heat and unverified recovery remain open. Use the [physical ledger](SM8850_LIVE_STATUS_2026-11-20.md) for current decisions.

This phase targets the Galaxy S26 Ultra SM-S948B / m3q / SM8850, Android 17 / One UI 9.
The phase uses the parent-pinned OneOS scripts and leaves SM8850 switching disabled.
The owner previously confirmed USB ADB and simultaneous physical Volume Up and
Volume Down. A physical watchdog handoff, return Gates A/B/C, and a verified guest
boot are pending. The [watchdog research](../app/docs/oneios-watchdog-recovery.md)
records the driver provenance gap.

## TODO and evidence

1. Verify the parent gitlink, OneOS HEAD and safety gate before running validation.
2. Run the isolated fixture in Bash and mksh against the pinned script bytes.
3. Verify the passive observer's ADB command scope with its offline transport tests.
4. Run OneOS Gradle tests and build the debug APK on CachyOS. Verify the packaged
   scripts match the pin and capture build and test counts.
5. Record the physical prerequisites that still block independent acceptance.

`scripts/phone/recovery-dry-run.py` reads the switch and return scripts and the
OneOS JUnit command stubs directly from the committed gitlink. Every case runs
in its own unprivileged Bubblewrap namespace. The sandbox has a minimal `/dev`,
an isolated network and PID namespace, and writable scratch space. The case
populates a synthetic `ONEIOS_TEST_ROOT` with process and namespace records,
cgroups, properties, fake watchdog ownership and USB files. A stepped sleep
fixture advances the real event-reader and polling timers one tick at a time.
The fixture changes inputs and checks outputs. The production scripts decide
when to send a request, which processes to clean up, and whether to return or
request a simulated reboot.

| Cases | Evidence checked |
| --- | --- |
| Two-key events and polling | Request absent before the 3-second tick and present at the threshold. The selector excludes the paired wearable and unrelated power-key input. |
| Single key, bounce, premature release | A single key cannot request a return. A brief release follows the production grace period. A longer release cancels the hold. |
| Watcher and races | One delivery and one framework restart for an active request. A late watcher ignores a request left behind by a completed return. A concurrent manual return defers to a live lock owner, and a reused PID is left alone. |
| Abnormal watcher or feeder exit | A dead watcher falls back to the key reader. An unavailable return script produces the simulated watcher failsafe. Loss of a previously ready feeder PID produces a recovery request and invalidates readiness. |
| Early and normal return | Shmem restores even before the stop marker. A normal return restores boot counters, preserves the persist property, cleans up PIDs when `cgroup.kill` is absent, and restores only the fixture's USB configuration before starting the framework. |
| Gates A/B/C | Positive path reaches a stable simulated unlock. Separate fixtures fail with a surviving session process, a composer that cannot restart, and an absent system server. |

Run the recovery checks from the parent checkout.

```sh
ONEOS_TEST_MKSH=/path/to/mksh \
ONEIOS_RECOVERY_REPORT=out/recovery/phase3.json \
scripts/ci-local.sh recovery
```

This CI mode runs offline observer tests, shell syntax checks, and the
production-script fixture. It needs Python 3, Bubblewrap with unprivileged
namespaces, Bash, mksh, and the initialized OneOS submodule at its parent pin.
Choose a new output filename on subsequent runs. To reproduce one scenario,
pass `--case` with a case ID to `recovery-dry-run.py`. The JSON report includes
case and check IDs, expected and actual values, statuses, shell versions,
script hashes, the synthetic fixture fingerprint, and physical blockers.
To attach a passive snapshot's fingerprint and checks, set
`ONEIOS_RECOVERY_OBSERVER_REPORT=out/recovery/s26-passive.json`. The snapshot
has its own SHA-256 and provenance in the combined report.

Run OneOS Gradle and APK checks with a staged guest manager artifact and the
dependencies already cached.

```sh
cd app/app-android
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk
export ANDROID_HOME="$HOME/Android/Sdk"
./gradlew --offline --console=plain --max-workers=3 --continue test \
  :core:model:test --rerun :core:safety:test --rerun \
  :core:root:testDebugUnitTest --rerun :app:assembleFullDebug
ONEOS_TEST_MKSH=/path/to/mksh ./gradlew --offline --console=plain --max-workers=3 \
  :core:root:testDebugUnitTest --tests '*StageScriptTest' --tests '*GuestRuntimeScriptTest'
```

## Safe manual hardware observation

1. Leave One UI running and unlocked. Use an already authorized USB ADB
   connection and select the S26 by its exact serial. Keep the device powered
   and skip sampling if the observer reports the target or framework as blocked.
2. From the parent checkout, create a local evidence directory and run the
   observer. Omit `--seconds` for the snapshot only.

   ```sh
   mkdir -p out/recovery
   python3 scripts/phone/observe-s26-recovery.py --serial YOUR_S26_SERIAL \
     --seconds 10 --output out/recovery/s26-passive.json
   ```

3. Skip key sampling if the volume chord already has an enabled accessibility
   shortcut. At “Sampling now,” hold **only** Volume Up and Volume Down together for
   four to five seconds, then release. The observer uses finite read-only
   `getevent -pl` calls on the two selected nodes. It records sampled key states
   with host monotonic timestamps and treats missing or slow samples as gaps.
   This measures sampled overlap. Hardware events between samples are unobserved.
4. If shell access to input is denied, the report marks it blocked. Where
   existing root access is already configured, the operator may rerun with
   `--root-input` and a new output filename. This applies only to the input
   inventory and the two `getevent` queries.

The observer reads firmware identity, input metadata and key-state samples,
USB/ADB state and framework presence. It references neither the OneOS scripts
nor their live session files. It issues no watchdog operation, sends no signal,
grabs no key and writes only the local JSON. The hardware report's fingerprint
comes from ADB. The fixture fingerprint is synthetic, with both evidence scopes
recorded independently.

Independent recovery acceptance still requires exact watchdog source and
driver-to-node attribution, proof of the real handoff and Gates A/B/C with a
recoverable test plan, and a matched verified iOS image and guest boot. USB
and key observations while One UI is running cannot establish those outcomes.
