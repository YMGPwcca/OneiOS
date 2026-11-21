#!/usr/bin/env bash
# Reproducible host-only CI for the 2026-11-21 direct-parent SM8850
# Oryon CPU placement + independent thermal telemetry port.
# No phone access, APFS rearm or Framework takeover is performed.
set -Eeuo pipefail
umask 077

ONEIOS="${ONEIOS_REPO:-$HOME/projects/OneiOS}"
ONEOS="${ONEOS_REPO:-$HOME/projects/OneiOS/app}"
IOS_BRANCH="feat/oneios-sm8850-m3q"
OS_BRANCH="feat/sm8850-p0-thermal-reader-sim"
IOS_PIN="bf5cd08f34f87804b3124fa09061cb3add5343d2"
OS_PIN="cfff2a3eb1a69e77a7810006b09b2c5feb5efaec"
JOBS="${JOBS:-8}"

case "$JOBS" in ''|*[!0-9]*) echo "REFUSED=JOBS_NOT_INTEGER" >&2; exit 2 ;; esac
test "$JOBS" -ge 1 && test "$JOBS" -le 16 || {
  echo "REFUSED=JOBS_OUTSIDE_1_TO_16" >&2; exit 2;
}
test -d "$ONEIOS/.git" && test -d "$ONEOS/.git" || {
  echo "REFUSED=LOCAL_GIT_CHECKOUT_MISSING" >&2; exit 2;
}
for required in git tar make python3; do
  command -v "$required" >/dev/null || {
    echo "REFUSED=MISSING_$required" >&2; exit 2;
  }
done

OUT="$ONEIOS/out/sm8850/parent-port-ci/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
LOG="$OUT/host-ci.log"
TMP=$(mktemp -d /tmp/oneios-parent-port-ci.XXXXXX)
trap 'rm -rf -- "$TMP"' EXIT

{
  echo "PHONE_ACTIONS=NONE"
  echo "ONEIOS_PARENT=akshaynexus/OneiOS @ 92886287724d3f9aa097dc17157281e585457500"
  echo "ONEIOS_SOURCE=$IOS_PIN"
  echo "ONEOS_SOURCE=$OS_PIN"
  echo "===== PINNED SOURCE CHECKS ====="
  git -C "$ONEIOS" fetch --no-tags origin "$IOS_BRANCH"
  git -C "$ONEOS" fetch --no-tags origin "$OS_BRANCH"
  git -C "$ONEIOS" cat-file -e "$IOS_PIN^{commit}"
  git -C "$ONEOS" cat-file -e "$OS_PIN^{commit}"
  git -C "$ONEIOS" merge-base --is-ancestor "$IOS_PIN" "refs/remotes/origin/$IOS_BRANCH"
  git -C "$ONEOS" merge-base --is-ancestor "$OS_PIN" "refs/remotes/origin/$OS_BRANCH"
  mkdir -p "$TMP/OneiOS" "$TMP/OneOS"
  git -C "$ONEIOS" archive "$IOS_PIN" | tar -xf - -C "$TMP/OneiOS"
  git -C "$ONEOS" archive "$OS_PIN" | tar -xf - -C "$TMP/OneOS"

  echo "===== ONEIOS BRIDGE Oryon CPU REGRESSION (HOST ONLY) ====="
  make -C "$TMP/OneiOS/runtime/bridges" -j "$JOBS" test

  echo "===== ONEIOS THERMAL REGRESSION (HOST ONLY) ====="
  make -C "$TMP/OneiOS/runtime/bridges/thermal" -j "$JOBS" test

  echo "===== ONEIOS XNUHOST HOST TESTS (NO PHONE) ====="
  make -C "$TMP/OneiOS/runtime/xnuhost" -j "$JOBS" test

  echo "===== ONEOS SM8850 P0 SOURCE / GUARD REGRESSION (NO PHONE) ====="
  (cd "$TMP/OneOS" && python3 -m unittest discover -s tests -p 'test_sm8850_thermal_shadow.py' -v)

  echo "SM8850_PARENT_PORT_LOCAL_CI=PASS_HOST_ONLY"
} > "$LOG" 2>&1 || {
  echo "SM8850_PARENT_PORT_LOCAL_CI=FAIL_HOST_ONLY"
  echo "HOST_CI_LOG=$LOG"
  tail -n 100 "$LOG" || :
  exit 1
}

echo "SM8850_PARENT_PORT_LOCAL_CI=PASS_HOST_ONLY"
echo "HOST_CI_LOG=$LOG"
