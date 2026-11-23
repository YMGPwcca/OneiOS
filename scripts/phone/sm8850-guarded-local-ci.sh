#!/usr/bin/env bash
# SM8850 guarded takeover OFFLINE CI: NO ADB, PHONE, SYSFS WRITES OR GUEST.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "===== EXACT SOURCE REVISIONS ====="
git rev-parse HEAD
test "$(git rev-parse HEAD:app)" = "$(git -C app rev-parse HEAD)" || {
    echo "BLOCKED=ONEOS_SUBMODULE_DOES_NOT_MATCH_ONEIOS_PIN" >&2
    exit 4
}
git -C app rev-parse HEAD
for src in \
    scripts/phone/sm8850-full-takeover.sh \
    scripts/phone/framework-stage.sh \
    app/switcher/assets/oneios_switch.sh \
    app/switcher/assets/oneios_return.sh \
    app/switcher/assets/oneios_sm8850_thermal_cap.sh \
    app/switcher/assets/oneios_sm8850_thermal_takeover_guard.sh; do
    if [[ "$src" == *.sh ]] && [[ "$src" == scripts/phone/sm8850-full-takeover.sh ]]; then
        bash -n "$src"
    else
        sh -n "$src"
    fi
done

echo "===== ONEOS THERMAL CONTRACT AND SYNTHETIC CPUFREQ ====="
python3 app/tests/test_sm8850_guarded_full.py -v

echo "===== ONEIOS OFFLINE RECOVERY/STAGING/FULL-RUN CONTRACTS ====="
for suite in \
    scripts/phone/test-sm8850-takeover.py \
    scripts/phone/test-sm8850-full-takeover.py \
    scripts/phone/test-sm8850-oneos-legacy-feeder.py \
    scripts/phone/test-sm8850-stage-upgrade.py \
    scripts/phone/test-sm8850-native-runtime-upgrade.py \
    scripts/phone/test-sm8850-guarded-duration.py; do
    python3 "$suite" -v
done

echo "===== NO-DEVICE TELEMETRY SELF TEST ====="
python3 -u scripts/phone/sm8850-600s-thermal-telemetry.py --self-test --duration 300
python3 -u scripts/phone/sm8850-600s-thermal-telemetry.py --self-test --duration 600

echo "GUARDED_TAKEOVER_OFFLINE_CI=PASS"
echo "PHYSICAL_SM8850_GUARD_WATCHDOG_QUALIFICATION=NOT_VERIFIED"
echo "LIVE_TAKEOVER_AUTHORIZED=NO"
