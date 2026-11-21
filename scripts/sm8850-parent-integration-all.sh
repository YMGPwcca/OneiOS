#!/usr/bin/env bash
# One command, two direct-parent forks, all OFFLINE source/build verification.
# No adb, root, APFS action, watchdog, reboot, Framework stop or guest takeover.
# Output is an artifact bundle + a single combined status report on CachyOS.
set -Eeuo pipefail
umask 077
[ "$(uname -s)" = Linux ] || { echo "REFUSED=LINUX_ONLY"; exit 2; }
[ "$(id -u)" != 0 ] || { echo "REFUSED=RUN_AS_NORMAL_USER"; exit 2; }

IOS="${ONEIOS_REPO:-$HOME/projects/OneiOS}"
OS="${ONEOS_REPO:-$HOME/projects/OneiOS/app}"
IOS_REF="feat/oneios-sm8850-m3q"
OS_REF="feat/sm8850-p0-thermal-reader-sim"
PARENT_IOS_PIN="a29dde8ffe81936476b619c6343f0beceded2f00"
PARENT_OS_PIN="53abb04e7bd87c785fff7a1db3ebd0742e777eb5"
JOBS="${JOBS:-8}"
VERSION="0.0.0-sm8850parity"
case "$JOBS" in ''|*[!0-9]*) echo "REFUSED=BAD_JOBS"; exit 2 ;; esac
[ "$JOBS" -ge 1 ] && [ "$JOBS" -le 16 ] || { echo "REFUSED=JOBS_OUT_OF_RANGE"; exit 2; }
for c in git bash python3 make sha256sum tar zstd; do
  command -v "$c" >/dev/null || { echo "REFUSED=MISSING_TOOL $c"; exit 2; }
done
for repo in "$IOS" "$OS"; do
  [ "$(git -C "$repo" rev-parse --is-inside-work-tree 2>/dev/null)" = true ] ||
    { echo "REFUSED=NOT_GIT_WORKTREE path=$repo"; exit 2; }
done
for spec in "$IOS|OneiOS" "$OS|OneOS"; do
  target=${spec%|*}; name=${spec#*|}
  u=$(git -C "$target" remote get-url origin)
  [[ "$u" =~ github\.com[:/]YMGPwcca/$name(\.git)?$ ]] ||
    { echo "REFUSED=UNEXPECTED_ORIGIN $target $u"; exit 2; }
done
OUT="$IOS/out/sm8850/parent-integration/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$OUT/artifacts"
STATUS="$OUT/status.env"
touch "$STATUS"
note() { printf '%s=%s\n' "$1" "$2" | tee -a "$STATUS"; }
run() {
  local name=$1; shift
  printf 'RUN=%s\n' "$name"
  if "$@" >"$OUT/$name.log" 2>&1; then
    note "$name" "PASS"
    return 0
  else
    local rc=$?
    note "$name" "FAIL_$rc"
    echo "LOG=$OUT/$name.log"
    tail -n 14 "$OUT/$name.log" || :
    return 1
  fi
}
echo "PHONE_ACTIONS=NONE"
echo "REPORT=$OUT"

# Exact branch snapshots: never checkout or reset the operator's working trees.
git -C "$IOS" fetch --no-tags origin "$IOS_REF" >"$OUT/fetch-ios.log" 2>&1 ||
  { echo "BLOCKED=FETCH_IOS; log=$OUT/fetch-ios.log"; exit 2; }
git -C "$OS" fetch --no-tags origin "$OS_REF" >"$OUT/fetch-os.log" 2>&1 ||
  { echo "BLOCKED=FETCH_OS; log=$OUT/fetch-os.log"; exit 2; }
IOS_SHA=$(git -C "$IOS" rev-parse "refs/remotes/origin/$IOS_REF")
OS_SHA=$(git -C "$OS" rev-parse "refs/remotes/origin/$OS_REF")
note IOS_SOURCE "$IOS_SHA"
note ONEOS_SOURCE "$OS_SHA"

# Fetch the DIRECT parents only. No merge: this is a review/provenance pin.
git -C "$IOS" fetch --no-tags https://github.com/akshaynexus/OneiOS.git main >"$OUT/fetch-parent-ios.log" 2>&1 ||
  { echo "BLOCKED=FETCH_DIRECT_PARENT_IOS"; exit 2; }
PARENT_IOS=$(git -C "$IOS" rev-parse FETCH_HEAD)
git -C "$OS" fetch --no-tags https://github.com/akshaynexus/OneOS.git oneios >"$OUT/fetch-parent-os.log" 2>&1 ||
  { echo "BLOCKED=FETCH_DIRECT_PARENT_OS"; exit 2; }
PARENT_OS=$(git -C "$OS" rev-parse FETCH_HEAD)
note DIRECT_PARENT_IOS "$PARENT_IOS"
note DIRECT_PARENT_ONEOS "$PARENT_OS"
if [ "$PARENT_IOS" = "$PARENT_IOS_PIN" ] && [ "$PARENT_OS" = "$PARENT_OS_PIN" ]; then
  note PARENT_DRIFT "NONE_FROM_REVIEWED_SOURCE"
else
  note PARENT_DRIFT "UNREVIEWED_NEW_PARENT_COMMITS"
fi
git -C "$IOS" diff --stat "$PARENT_IOS" "$IOS_SHA" >"$OUT/parent-ios-diffstat.txt" 2>&1 || :
git -C "$OS" diff --stat "$PARENT_OS" "$OS_SHA" >"$OUT/parent-os-diffstat.txt" 2>&1 || :

WORK=$(mktemp -d "$OUT/work.XXXXXX")
cleanup() {
  git -C "$IOS" worktree remove --force "$WORK/OneiOS" >/dev/null 2>&1 || :
  git -C "$OS" worktree remove --force "$WORK/OneOS" >/dev/null 2>&1 || :
  rm -rf -- "$WORK"
}
trap cleanup EXIT
git -C "$IOS" worktree add --detach "$WORK/OneiOS" "$IOS_SHA" >"$OUT/worktree-ios.log" 2>&1 ||
  { echo "BLOCKED=WORKTREE_IOS"; exit 2; }
git -C "$OS" worktree add --detach "$WORK/OneOS" "$OS_SHA" >"$OUT/worktree-os.log" 2>&1 ||
  { echo "BLOCKED=WORKTREE_OS"; exit 2; }

# Reuse pre-existing pinned reference clones and iOS stubs as read-only
# source input; the worktree has its own output directory and test results.
# Link existing pinned dependency directories individually, not the entire
# external/ folder. New missing clones stay inside the disposable worktree
# instead of modifying the operator's main checkout.
mkdir -p "$WORK/OneiOS/external"
if [ -d "$IOS/external" ]; then
  for reference in "$IOS"/external/*; do
    [ -d "$reference" ] || continue
    name=$(basename "$reference")
    expected=""
    case "$name" in
      virglrenderer) expected=7e17c8e814e963912fc1e4e737137a31b5efa027 ;;
      Droid-VM-UniXNU) expected=62d0b11773ec17561fb409ed6e4c5adfa29ff45b ;;
      NativeMetal) expected=b0d6a07a3da3e23486593aff235904177e94a3ff ;;
      NativeAdreno) expected=627836d507ef08037fff2f9b12e9274ba7b2a4f3 ;;
      NativeMobileDisplay) expected=ed08bd437b93772d4c41d74633af12446918f18a ;;
      AdrenoPM4) expected=282606b528b2595bc4274ea7490b62b323f35a5f ;;
      metal2vulkan) expected=624bab3918de5b978e1101517abca2b4fa426565 ;;
      mesa-droidvm) expected=cecc0e96d7193c72356a31abb0cc589e4fc0415e ;;
    esac
    if [ -n "$expected" ] && [ "$(git -C "$reference" rev-parse HEAD 2>/dev/null || echo missing)" != "$expected" ]; then
      printf 'REF_PIN_DRIFT=%s; fetching isolated pinned clone if required\n' "$name" >>"$OUT/reference-pins.log"
      continue
    fi
    ln -s "$reference" "$WORK/OneiOS/external/$name"
  done
fi
export JOBS
if run STATIC_PARITY env ONEOS_REPO="$WORK/OneOS" python3 "$WORK/OneiOS/scripts/phone/test-sm8850-parent-parity.py"; then
  static_ok=1
else
  static_ok=0
fi
if run ONEOS_P0_ALL bash "$WORK/OneOS/tests/run_sm8850_thermal_local.sh"; then
  os_ok=1
else
  os_ok=0
fi

# Existing full local CI is the canonical source+host+Android ARM64 runtime
# pipeline. It fetches the pinned 3D virglrenderer, refuses 2D-only binaries,
# runs host tests once, packages runtime, verifies SHA and ELF dependencies.
if [ "$static_ok" = 1 ] && [ "$os_ok" = 1 ]; then
  # An existing ignored external checkout must be exactly the pinned GPU
  # reference. get-references.sh deliberately does not overwrite old clones.
  virgl="$WORK/OneiOS/external/virglrenderer"
  if [ -d "$virgl" ] &&
     [ "$(git -C "$virgl" rev-parse HEAD 2>/dev/null)" != "7e17c8e814e963912fc1e4e737137a31b5efa027" ]; then
    note ONEIOS_ALL "BLOCKED_VIRGLRENDERER_PIN_MISMATCH"
    echo "BLOCKED=VIRGL_PIN expected=7e17c8e814e963912fc1e4e737137a31b5efa027 actual=$(git -C "$virgl" rev-parse HEAD 2>/dev/null || echo none)"
    runtime_ok=0
  elif run ONEIOS_ALL env JOBS="$JOBS" bash "$WORK/OneiOS/scripts/ci-local.sh" all "$VERSION"; then
    runtime_ok=1
    runtime="$WORK/OneiOS/out/release/oneios-runtime-$VERSION-arm64.tar.zst"
    [ -s "$runtime" ] && [ -s "$runtime.sha256" ] ||
      { runtime_ok=0; note RUNTIME_ARTIFACT "MISSING"; }
    if [ "$runtime_ok" = 1 ]; then
      cp -- "$runtime" "$runtime.sha256" "$OUT/artifacts/"
      (cd "$OUT/artifacts" && sha256sum -c "$(basename "$runtime").sha256") >"$OUT/runtime-sha256.log" 2>&1 ||
        { runtime_ok=0; note RUNTIME_ARTIFACT "HASH_MISMATCH"; }
      [ "$runtime_ok" != 1 ] || note RUNTIME_GPU3D "PASS_VERIFIED_ARM64_ARCHIVE"
    fi
  else
    runtime_ok=0
  fi
else
  runtime_ok=0
  note ONEIOS_ALL "BLOCKED_EARLIER_SOURCE_TESTS"
fi

# Separate Android app source gate: read-only OneOS Probe debug APK and JVM
# tests. Never build, sign or install a privileged SM8850 OneOS switch APK.
app_ok=0
if run ONEOS_APP_PROBE bash -c '
  set -euo pipefail
  cd "$1/app-android"
  ./gradlew --no-daemon --max-workers=3 :core:model:test :core:safety:test :core:root:testDebugUnitTest :app:assembleProbeDebug
' _ "$WORK/OneOS"; then
  apk="$WORK/OneOS/app-android/app/build/outputs/apk/probe/debug/app-probe-debug.apk"
  if [ -s "$apk" ]; then
    cp -- "$apk" "$OUT/artifacts/"
    app_ok=1
    note ONEOS_PROBE_APK "PASS_DEBUG_READONLY_PROBE"
  else
    note ONEOS_PROBE_APK "FAIL_OUTPUT_MISSING"
  fi
fi

# Preserve Gradle test XML/HTML before deleting the worktree. The Gradle
# tail alone does not identify the failing tests.
GRADLE_SOURCE="$WORK/OneOS/app-android"
GRADLE_XML="$OUT/gradle-test-results"
GRADLE_HTML="$OUT/gradle-html-reports"
mkdir -p "$GRADLE_XML" "$GRADLE_HTML"
while IFS= read -r -d '' report; do
  relative=${report#"$GRADLE_SOURCE/"}
  destination="$GRADLE_XML/$relative"
  mkdir -p "$(dirname "$destination")"
  cp -- "$report" "$destination"
done < <(find "$GRADLE_SOURCE" -type f -name 'TEST-*.xml' -path '*/build/test-results/*' -print0)
while IFS= read -r -d '' report; do
  relative=${report#"$GRADLE_SOURCE/"}
  destination="$GRADLE_HTML/$relative"
  mkdir -p "$(dirname "$destination")"
  cp -- "$report" "$destination"
done < <(find "$GRADLE_SOURCE" -type f -path '*/build/reports/tests/*' -print0)
python3 - "$GRADLE_XML" "$OUT/ONEOS_GRADLE_FAILURES.txt" <<'PY'
from pathlib import Path
import sys
from xml.etree import ElementTree

root = Path(sys.argv[1])
target = Path(sys.argv[2])
reports = sorted(root.rglob("TEST-*.xml"))
failures = []
tests = 0
for report in reports:
    try:
        tree = ElementTree.parse(report)
        for test in tree.iter("testcase"):
            tests += 1
            for kind in ("failure", "error"):
                for issue in test.findall(kind):
                    reason = " ".join((issue.get("message") or "").split())
                    detail = " ".join((issue.text or "").split())
                    failures.append(
                        f"{test.get('classname', '?')}.{test.get('name', '?')}"
                        f" ({kind}): {reason or detail[:400]}"
                    )
    except (OSError, ElementTree.ParseError) as exc:
        failures.append(f"COULD_NOT_PARSE {report}: {exc}")
lines = [
    f"GRADLE_TEST_XML_FILES={len(reports)}",
    f"GRADLE_TEST_CASES={tests}",
    f"GRADLE_FAILED_TESTS={len(failures)}",
]
lines += ("GRADLE_FAILED_TEST=" + item for item in failures)
target.write_text("\n".join(lines) + "\n")
print("===== PRESERVED ONEOS JUNIT DIAGNOSTICS =====")
for line in lines[:15]:
    print(line[:900])
print(f"GRADLE_TEST_REPORT={target}")
PY
if [ "$app_ok" = 0 ]; then
  note ONEOS_APP_DIAGNOSTICS "PRESERVED_TEST_XML_HTML_AND_FAILURE_SUMMARY"
else
  note ONEOS_APP_DIAGNOSTICS "PRESERVED_TEST_XML_HTML"
fi

# Metal/Turnip is a separate iOS 27 arm64e build: it requires a previously
# installed iPhoneOS SDK and ld64/stubs. Attempt all dependencies once and
# produce ONE grouped report. Do not silently call a 2D runtime a Metal PASS.
metal_build() (
  set -Eeuo pipefail
  cd "$WORK/OneiOS"
  mkdir -p external
  # The kernel pin-fetch code enforces an exact Droid-VM-UniXNU revision.
  . kernel/pins.sh
  pin_fetch "$PWD/external" Droid-VM-UniXNU \
    https://github.com/Droid-VM/UniXNU.git \
    62d0b11773ec17561fb409ed6e4c5adfa29ff45b wip/droidvm
  scripts/setup/get-references.sh NativeMetal NativeAdreno NativeMobileDisplay AdrenoPM4 metal2vulkan mesa-droidvm
  # Do not silently build an unrelated Mesa/Turnip/Metal revision because an
  # older external clone happens to exist on this developer's machine.
  while read -r name commit; do
    actual=$(git -C "external/$name" rev-parse HEAD 2>/dev/null || echo "missing")
    [ "$actual" = "$commit" ] || { echo "METAL_PIN_MISMATCH=$name expected=$commit actual=$actual"; return 4; }
  done <<'PINS'
NativeMetal b0d6a07a3da3e23486593aff235904177e94a3ff
NativeAdreno 627836d507ef08037fff2f9b12e9274ba7b2a4f3
NativeMobileDisplay ed08bd437b93772d4c41d74633af12446918f18a
AdrenoPM4 282606b528b2595bc4274ea7490b62b323f35a5f
metal2vulkan 624bab3918de5b978e1101517abca2b4fa426565
mesa-droidvm cecc0e96d7193c72356a31abb0cc589e4fc0415e
PINS
  export IOS_LD="${IOS_LD:-$IOS/out/ios-toolchain/cctools/bin/ld}"
  export IOS_TBD="${IOS_TBD:-$IOS/out/ios27-tbd}"
  export METAL_OUT="$OUT/artifacts/metal"
  export METAL_WORK="$OUT/metal-work"
  bash userland/metal/build.sh all
  test -s "$METAL_OUT/NativeAdrenoMetal.gpuaddon"
  test -s "$METAL_OUT/NativeAdrenoMetal.build.json"
  test -s "$METAL_OUT/NativeAdrenoMetal.bundle/NativeAdrenoMetal"
)
if run METAL_IOS27 metal_build; then
  metal_ok=1
  note METAL_ARTIFACT "PASS_ARM64E_BUNDLE_AND_GPUADDON"
else
  metal_ok=0
  note METAL_ARTIFACT "BLOCKED_OR_FAILED_SEE_SINGLE_METAL_LOG"
fi

find "$OUT/artifacts" -type f -print0 | sort -z | xargs -0 -r sha256sum > "$OUT/SHA256SUMS"
printf 'PHONE_ACTIONS=NONE\n' >> "$STATUS"
python3 - "$OUT" <<'PY'
import json, pathlib, sys
out=pathlib.Path(sys.argv[1])
entries={}
for line in (out/"status.env").read_text().splitlines():
    if "=" in line:
        k,v=line.split("=",1)
        entries[k]=v
entries["evidence"]="local source/build only; physical thermal/recovery not certified"
entries["operator_phone_actions"]=False
(out/"report.json").write_text(json.dumps(entries,indent=2,sort_keys=True)+"\n")
PY
echo "===== CONSOLIDATED RESULT ====="
cat "$STATUS"
echo "ARTIFACT_DIR=$OUT/artifacts"
echo "SHA256_MANIFEST=$OUT/SHA256SUMS"
echo "REPORT_JSON=$OUT/report.json"
if [ "$static_ok" = 1 ] && [ "$os_ok" = 1 ] && [ "$runtime_ok" = 1 ] &&
   [ "$app_ok" = 1 ] && [ "$metal_ok" = 1 ] &&
   [ "$PARENT_IOS" = "$PARENT_IOS_PIN" ] && [ "$PARENT_OS" = "$PARENT_OS_PIN" ]; then
  echo "SM8850_PARENT_INTEGRATION=PASS_OFFLINE_NO_PHONE"
else
  echo "SM8850_PARENT_INTEGRATION=PARTIAL_OR_BLOCKED_REPORT_ALL_LOGS"
  exit 3
fi
