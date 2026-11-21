#!/usr/bin/env bash
# Single-command offline acceptance after the 2026-11-21 GPU3D+Metal PASS.
# Reuses the exact hashed runtime/Metal from the user's previous integrated
# build ONLY if both forks' diffs are in narrowly scoped non-runtime paths.
# Otherwise automatically runs the full, existing integration pipeline.
# PHONE_ACTIONS=NONE: no ADB, rearm, reboot or Framework takeovers.
set -Eeuo pipefail
umask 077

IOS="${ONEIOS_REPO:-$HOME/projects/OneiOS}"
OS="${ONEOS_REPO:-$HOME/projects/OneiOS/app}"
IOS_BRANCH="feat/oneios-sm8850-m3q"
OS_BRANCH="feat/sm8850-p0-thermal-reader-sim"
OLD_IOS="c671463abc53215b3a6cb5b09a6d4612fa618418"
OLD_OS="14322105bebd6b83e38e10bb4da5aeba53b2b5c6"
CACHE="${SM8850_CACHED_REPORT:-$IOS/out/sm8850/parent-integration/20261121T095241Z-1269097}"

echo "PHONE_ACTIONS=NONE"
for tool in git bash python3 sha256sum grep find; do
  command -v "$tool" >/dev/null || { echo "REFUSED=MISSING_TOOL_$tool"; exit 2; }
done
test "$(id -u)" != 0 || { echo "REFUSED=ROOT_NOT_ALLOWED"; exit 2; }
for dir in "$IOS" "$OS"; do
  test "$(git -C "$dir" rev-parse --is-inside-work-tree 2>/dev/null)" = true ||
    { echo "REFUSED=CHECKOUT_NOT_FOUND path=$dir"; exit 2; }
done
git -C "$IOS" fetch --no-tags origin "$IOS_BRANCH"
git -C "$OS" fetch --no-tags origin "$OS_BRANCH"
IOS_SHA=$(git -C "$IOS" rev-parse "refs/remotes/origin/$IOS_BRANCH")
OS_SHA=$(git -C "$OS" rev-parse "refs/remotes/origin/$OS_BRANCH")
echo "ONEIOS_SOURCE=$IOS_SHA"
echo "ONEOS_SOURCE=$OS_SHA"

full() {
  echo "CACHE_REUSE=REFUSED_CHANGED_SOURCE_OR_MISSING_HASHES"
  echo "FALLBACK=COMPLETE_OFFLINE_PIPELINE"
  git -C "$IOS" cat-file blob "$IOS_SHA:scripts/sm8850-parent-integration-all.sh" | bash -n
  git -C "$IOS" cat-file blob "$IOS_SHA:scripts/sm8850-parent-integration-all.sh" | bash
}

allow_diff() {
  local repo=$1 old=$2 new=$3 kind=$4 line
  git -C "$repo" merge-base --is-ancestor "$old" "$new" || return 1
  while IFS= read -r line; do
    case "$kind:$line" in
      ios:docs/*|ios:scripts/sm8850-parent-integration-all.sh|\
      ios:scripts/sm8850-parent-integration-resume.sh|\
      ios:scripts/phone/test-sm8850-parent-parity.py|\
      os:docs/*|os:app-android/*) ;;
      *) [ -z "$line" ] || { echo "CACHE_REJECTED_CHANGE=$line"; return 1; } ;;
    esac
  done < <(git -C "$repo" diff --name-only "$old" "$new")
}

source_same=0
if allow_diff "$IOS" "$OLD_IOS" "$IOS_SHA" ios &&
   allow_diff "$OS" "$OLD_OS" "$OS_SHA" os; then
  source_same=1
fi

cached_receipts_ok=0
if [ "$source_same" = 1 ] &&
   [ -f "$CACHE/status.env" ] && [ -s "$CACHE/SHA256SUMS" ] &&
   grep -qx "IOS_SOURCE=$OLD_IOS" "$CACHE/status.env" &&
   grep -qx "ONEOS_SOURCE=$OLD_OS" "$CACHE/status.env" &&
   grep -qx 'STATIC_PARITY=PASS' "$CACHE/status.env" &&
   grep -qx 'ONEOS_P0_ALL=PASS' "$CACHE/status.env" &&
   grep -qx 'ONEIOS_ALL=PASS' "$CACHE/status.env" &&
   grep -qx 'RUNTIME_GPU3D=PASS_VERIFIED_ARM64_ARCHIVE' "$CACHE/status.env" &&
   grep -qx 'METAL_IOS27=PASS' "$CACHE/status.env" &&
   grep -qx 'METAL_ARTIFACT=PASS_ARM64E_BUNDLE_AND_GPUADDON' "$CACHE/status.env" &&
   [ -s "$CACHE/artifacts/metal/NativeAdrenoMetal.gpuaddon" ] &&
   [ -s "$CACHE/artifacts/metal/NativeAdrenoMetal.build.json" ] &&
   find "$CACHE/artifacts" -maxdepth 1 -name 'oneios-runtime-*-arm64.tar.zst' -type f | grep -q . &&
   sha256sum --status -c "$CACHE/SHA256SUMS" 2>/dev/null; then
  cached_receipts_ok=1
fi

if [ "$cached_receipts_ok" != 1 ]; then
  full
  exit $?
fi

OUT="$IOS/out/sm8850/parent-resume/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$OUT/artifacts" "$OUT/gradle-test-results" "$OUT/gradle-html-reports"
STATUS="$OUT/status.env"
note() { printf '%s=%s\n' "$1" "$2" | tee -a "$STATUS"; }
note PHONE_ACTIONS NONE
note CACHE_REUSE VERIFIED_SHA256_AND_SCOPED_GIT_DIFF
note ORIGINAL_REPORT "$CACHE"
note IOS_SOURCE "$IOS_SHA"
note ONEOS_SOURCE "$OS_SHA"
note ONEIOS_ALL PASS_REUSED_VERIFIED_PINNED_GPU3D
note METAL_IOS27 PASS_REUSED_VERIFIED_PINNED_ARM64E
note ONEOS_P0_ALL PASS_REUSED_UNCHANGED_SWITCHER_AND_P0_TESTS

WORK=$(mktemp -d "$OUT/work.XXXXXX")
cleanup() {
  git -C "$IOS" worktree remove --force "$WORK/OneiOS" >/dev/null 2>&1 || :
  git -C "$OS" worktree remove --force "$WORK/OneOS" >/dev/null 2>&1 || :
  rm -rf -- "$WORK"
}
trap cleanup EXIT
git -C "$IOS" worktree add --detach "$WORK/OneiOS" "$IOS_SHA" > "$OUT/worktree-ios.log" 2>&1
git -C "$OS" worktree add --detach "$WORK/OneOS" "$OS_SHA" > "$OUT/worktree-oneos.log" 2>&1

if ONEOS_REPO="$WORK/OneOS" python3 "$WORK/OneiOS/scripts/phone/test-sm8850-parent-parity.py" > "$OUT/STATIC_PARITY.log" 2>&1; then
  static_ok=1
  note STATIC_PARITY PASS_CURRENT_SOURCE
else
  static_ok=0
  note STATIC_PARITY FAIL
  tail -n 45 "$OUT/STATIC_PARITY.log" || :
fi

app_ok=0
gradle_root="$WORK/OneOS/app-android"
if (cd "$gradle_root" &&
    ./gradlew --no-daemon --console=plain --continue --max-workers=3 \
      :core:model:test :core:safety:test :core:root:testDebugUnitTest :app:assembleProbeDebug
  ) > "$OUT/ONEOS_APP_PROBE.log" 2>&1; then
  app_ok=1
  note ONEOS_APP_PROBE PASS_ALL_JUNIT_AND_APK_TASKS
else
  note ONEOS_APP_PROBE FAIL_JUNIT_OR_BUILD
  tail -n 22 "$OUT/ONEOS_APP_PROBE.log" || :
fi

apk="$gradle_root/app/build/outputs/apk/probe/debug/app-probe-debug.apk"
if [ -s "$apk" ]; then
  cp -- "$apk" "$OUT/artifacts/"
  (cd "$OUT/artifacts" && sha256sum app-probe-debug.apk > app-probe-debug.apk.sha256)
  note ONEOS_PROBE_APK BUILT_DEBUG_READONLY_PROBE
else
  note ONEOS_PROBE_APK NOT_BUILT
  app_ok=0
fi

python3 - "$gradle_root" "$OUT" <<'PY'
import pathlib, shutil, sys, xml.etree.ElementTree as ET
root, out = map(pathlib.Path, sys.argv[1:])
xmls = []
for path in root.rglob("TEST-*.xml"):
    if "/build/test-results/" not in path.as_posix():
        continue
    dst = out / "gradle-test-results" / path.relative_to(root)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)
    xmls.append(dst)
for path in root.rglob("*"):
    if not path.is_file() or "/build/reports/tests/" not in path.as_posix():
        continue
    dst = out / "gradle-html-reports" / path.relative_to(root)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)
failed = []
cases = 0
for p in xmls:
    try:
        for test in ET.parse(p).iter("testcase"):
            cases += 1
            for kind in ("failure", "error"):
                for issue in test.findall(kind):
                    label = f"{test.get('classname','?')}.{test.get('name','?')}"
                    msg = (issue.attrib.get("message") or "").strip()
                    stack = (issue.text or "").strip()
                    failed.append((label,kind,msg,stack))
    except (OSError,ET.ParseError) as exc:
        failed.append((str(p),"parse-error",str(exc),""))
full = [f"XML_FILES={len(xmls)}",f"TEST_CASES={cases}",f"FAILED_TESTS={len(failed)}"]
for label, kind, message, stack in failed:
    full.extend((f"FAIL={label} [{kind}]",f"MESSAGE={message}",f"STACK={stack}","---"))
report = out / "ONEOS_GRADLE_FAILURES.txt"
report.write_text("\n".join(full)+"\n")
print("===== ONEOS JUNIT SUMMARY =====")
for line in full:
    if line.startswith(("XML_FILES=","TEST_CASES=","FAILED_TESTS=","FAIL=","MESSAGE=")):
        print(line[:2500])
print(f"GRADLE_FAILURE_REPORT={report}")
PY

note JUNIT_REPORT "$OUT/ONEOS_GRADLE_FAILURES.txt"
note GPU3D_ARTIFACTS "$CACHE/artifacts"
note GPU3D_METAL_SHA256_MANIFEST "$CACHE/SHA256SUMS"
python3 - "$OUT" <<'PY'
import json, pathlib, sys
out=pathlib.Path(sys.argv[1])
status=dict(line.split("=",1) for line in (out/"status.env").read_text().splitlines() if "=" in line)
status["physical_thermal_and_unattended_recovery_certified"]=False
status["phone_actions"]=False
(out/"report.json").write_text(json.dumps(status,indent=2,sort_keys=True)+"\n")
PY
echo "REPORT_JSON=$OUT/report.json"
echo "GRADLE_FAILURE_REPORT=$OUT/ONEOS_GRADLE_FAILURES.txt"
if [ "$static_ok" = 1 ] && [ "$app_ok" = 1 ]; then
  echo "SM8850_PARENT_INTEGRATION=PASS_OFFLINE_CACHED_GPU3D_METAL_REVALIDATED_ONEOS"
else
  echo "SM8850_PARENT_INTEGRATION=PARTIAL_ONEOS_JUNIT_OR_STATIC_FAILURE"
  exit 3
fi
