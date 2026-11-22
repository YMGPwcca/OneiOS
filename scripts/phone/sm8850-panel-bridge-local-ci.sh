#!/usr/bin/env bash
# SM8850 isolated panel bridge: local-only compile/test, NEVER phone access.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
test "$(git branch --show-current)" = feat/sm8850-isolated-panel-bridge
test "$(git -C app branch --show-current)" = "" || {
  echo "BLOCKED: app submodule is not detached at the pinned commit" >&2
  exit 2
}
echo "===== EXACT SOURCES ====="
git rev-parse HEAD
git -C app rev-parse HEAD
echo "===== SHELL / PYTHON SYNTAX ====="
sh -n app/switcher/assets/oneios_switch.sh
sh -n app/switcher/assets/oneios_sm8850_thermal_cap.sh
python3 -m py_compile app/tests/test_sm8850_guarded_full.py
echo "===== ONEOS OFFLINE CONTRACT ====="
python3 app/tests/test_sm8850_guarded_full.py -v
echo "===== XNUHOST PORTABLE C TEST BUILD ====="
make -C runtime/xnuhost -j"${JOBS:-8}" build/host/test_xnuhost
echo "===== XNUHOST PORTABLE C TEST ====="
(cd runtime/xnuhost && ASAN_OPTIONS=detect_leaks=0 ./build/host/test_xnuhost)
echo "SM8850_PANEL_BRIDGE_LOCAL_CI=PASS_NO_DEVICE_ACCESS"
echo "ARM64_NATIVE_RUNTIME=NOT_BUILT_BY_THIS_SCRIPT"
echo "FRAMEWORK_STOP=NO APFS_REARM=NO LIVE_TAKEOVER=NO"
