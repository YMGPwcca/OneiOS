#!/usr/bin/env bash
# Standalone OneiOS CI: poll the trusted branch and build changed commits locally.
# No GitHub Actions, runner token, adb, su, sudo, or phone control.
# Usage: scripts/ci-watch.sh [once|force|status]
set -euo pipefail

export PATH="$HOME/.cargo/bin:$PATH"
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CI_HOME=${ONEIOS_CI_HOME:-"$HOME/oneios-m3q-ci/standalone"}
REF=${ONEIOS_CI_REF:-refs/heads/feat/oneios-sm8850-m3q}
ACTION=${1:-once}

case "$ACTION" in
  once|force|status) ;;
  *) echo "usage: $0 [once|force|status]" >&2; exit 2 ;;
esac

mkdir -p "$CI_HOME/runs"
STATE="$CI_HOME/last-result.txt"

if [ "$ACTION" = status ]; then
  if [ -f "$STATE" ]; then
    cat "$STATE"
    sha=$(sed -n 's/^commit=//p' "$STATE" | head -n 1)
    [ -z "$sha" ] || echo "log=$CI_HOME/runs/$sha/run.log"
  else
    echo "ci-watch: no commit tested yet"
  fi
  exit 0
fi

command -v flock >/dev/null || { echo 'ci-watch: missing util-linux flock' >&2; exit 1; }
exec 9>"$CI_HOME/.lock"
if ! flock -n 9; then
  echo 'ci-watch: another local CI run is active; skipping this poll'
  exit 0
fi

# Fetch exactly the configured trusted branch, never a pull-request ref.
git -C "$REPO" fetch --no-tags origin "$REF"
sha=$(git -C "$REPO" rev-parse --verify 'FETCH_HEAD^{commit}')
previous=$(sed -n 's/^commit=//p' "$STATE" 2>/dev/null | head -n 1 || true)
if [ "$ACTION" != force ] && [ "$sha" = "$previous" ]; then
  echo "ci-watch: $sha already tested; no new commit"
  exit 0
fi

RUN="$CI_HOME/runs/$sha"
mkdir -p "$RUN/artifacts"
WORKTREE="$CI_HOME/.worktree-$sha-$$"
cleanup() {
  if [ -e "$WORKTREE/.git" ]; then
    git -C "$REPO" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

git -C "$REPO" worktree add --detach "$WORKTREE" "$sha"
printf 'ci-watch: testing %s\n' "$sha"
printf 'started=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$RUN/started.txt"

# Capture the complete output while preserving the actual test exit status.
set +e
( cd "$WORKTREE" && ./scripts/ci-local.sh all 0.0.0-ci ) 2>&1 | tee "$RUN/run.log"
result=("${PIPESTATUS[@]}")
set -e
rc=${result[0]}
[ "${result[1]}" -eq 0 ] || rc=1

if [ -d "$WORKTREE/out/release" ]; then
  for artifact in "$WORKTREE"/out/release/oneios-runtime-0.0.0-ci-arm64.tar.zst* \
                  "$WORKTREE"/out/release/oneios-runtime-0.0.0-ci-arm64.runtime.json; do
    [ -f "$artifact" ] || continue
    cp -f "$artifact" "$RUN/artifacts/" || rc=1
  done
fi

finished=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
if [ "$rc" -eq 0 ]; then verdict=PASS; else verdict=FAIL; fi
printf 'commit=%s\nresult=%s\nexit_code=%s\nfinished=%s\n' \
  "$sha" "$verdict" "$rc" "$finished" > "$RUN/result.txt"
# Remember failures too: a broken commit should not retry every minute.
cp "$RUN/result.txt" "$STATE.tmp.$$"
mv -f "$STATE.tmp.$$" "$STATE"
printf 'ci-watch: %s %s; log=%s; artifacts=%s\n' \
  "$sha" "$verdict" "$RUN/run.log" "$RUN/artifacts"
exit "$rc"
