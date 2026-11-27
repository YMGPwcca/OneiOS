#!/usr/bin/env bash
# One local entry for the stock thermal source/controller/HAL batch and
# the previously committed performance/runtime regressions. No ADB or device.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
test "$(git rev-parse HEAD:app)" = "$(git -C app rev-parse HEAD)"
echo "ONEIOS=$(git rev-parse HEAD)"
echo "ONEOS=$(git -C app rev-parse HEAD)"
export ANDROID_NDK_ROOT="${ANDROID_NDK_ROOT:-${NDK:-$HOME/Android/Sdk/ndk/28.2.13676358}}"
export NDK="$ANDROID_NDK_ROOT"
NDK_CC="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang"
test -x "$NDK_CC"
CC="${CC:-cc}"
OUT="$(mktemp -d /tmp/oneios-stock-thermal-ci.XXXXXX)"
echo "STOCK_BUILD_EVIDENCE=$OUT"
N=app/switcher/native
T=app/tests
echo "===== ONEOS BOOTANIM AND ADMISSION ====="
sh -n app/switcher/assets/oneios_switch.sh
sh -n app/switcher/assets/oneios_return.sh
python3 "$T/test_sm8850_bootanim.py"
python3 "$T/test_sm8850_perf_profile.py"
python3 "$T/test_sm8850_guarded_full.py"
python3 scripts/phone/test-sm8850-full-takeover.py
python3 -m unittest discover -s app/tools -p test_sm8850_adaptive_thermal.py
echo "===== OWNED GROUPS / CONTROLLER / PINNED RAW SOURCE ====="
"$CC" -std=gnu11 -O2 -g -Wall -Wextra -Werror \
    "$T/test_sm8850_owned_groups.c" -pthread -o "$OUT/groups"
"$OUT/groups"
"$CC" -std=gnu11 -O2 -g -Wall -Wextra -Werror -DONEIOS_RAW_SOURCE_TEST \
    "$T/test_sm8850_thermal_controller.c" "$N/sm8850_thermal_controller.c" \
    "$N/sm8850_thermal_source.c" -o "$OUT/controller"
"$OUT/controller"
python3 "$T/test_sm8850_thermal_policy_parity.py" "$OUT/controller"
python3 "$T/test_sm8850_stock_source.py" "$OUT/controller"
for unit in sm8850_owned_groups sm8850_thermal_controller sm8850_thermal_source; do
    "$NDK_CC" -std=gnu11 -O2 -g -Wall -Wextra -Werror \
        -c "$N/$unit.c" -o "$OUT/$unit.o"
done
echo "ONEOS_ANDROID_NATIVE_COMPILE=PASS"
echo "===== THERMAL BRIDGE AND TYPED NATIVE HAL ====="
make -C runtime/bridges/thermal test stock-test all
python3 scripts/phone/sm8850-native-thermal-observe.py --self-test
echo "===== FULL LOCAL PERFORMANCE RUNTIME / PACKAGE ====="
JOBS="${JOBS:-8}" bash scripts/ci-local.sh all "0.0.0-stock.$(git rev-parse --short HEAD)"
echo "STOCK_SOURCE_BATCH_OFFLINE=PASS"
echo "DEVICE_ACCESS=NONE"
echo "LIVE_TAKEOVER_AUTHORIZED=NO"
