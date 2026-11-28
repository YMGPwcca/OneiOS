#!/usr/bin/env bash
# Consolidated host-only integration regression from matching source exports.
# Never ADB, stage, flash, or stop Android.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
R=$PWD
D=$(mktemp -d /tmp/oneios-stock-e2e.XXXXXX)
echo "EVIDENCE=$D"
N=$R/app/switcher/native
S=$R/runtime/xnuhost/src
T=$R/runtime/xnuhost/tests
test -f "$N/sm8850_stock_session.c"
test -f "$R/runtime/bridges/battery/battery.h"
CC="${CC:-cc}"
common=(-std=gnu11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -pthread
  -I"$S" -I"$N" -I"$R/runtime/xnuhost/include" -I"$R/runtime/xnuhost/stub"
  -I"$R/runtime/loader/include" -I"$R/runtime/bridges/include"
  -I"$R/runtime/bridges/encoder" -I"$R/drivers/bridge" -I"$R/drivers/camera")
export ASAN_OPTIONS=detect_leaks=0
echo "===== SUPERVISOR / BOARD REGRESSION ====="
make -C "$R/runtime/xnuhost" -j"${JOBS:-8}" \
  build/host/test_quiesce_supervisor build/host/test_quiesce_board \
  build/host/test_quiesce_board_worker
"$R/runtime/xnuhost/build/host/test_quiesce_supervisor"
"$R/runtime/xnuhost/build/host/test_quiesce_board"
"$R/runtime/xnuhost/build/host/test_quiesce_board_worker"
echo "===== STOCK SESSION COMPATIBILITY ====="
"$CC" "${common[@]}" "$R/app/tests/test_sm8850_stock_session.c" \
  "$N/sm8850_stock_session.c" "$N/sm8850_thermal_controller.c" \
  -o "$D/session"
"$D/session"
echo "===== STOCK CONTROLLER / SUPERVISOR ====="
"$CC" "${common[@]}" "$T/test_stock_thermal_supervisor.c" \
  "$S/stock_thermal_supervisor.c" "$S/quiesce_supervisor.c" "$S/quiesce.c" \
  "$N/sm8850_thermal_controller.c" -o "$D/stock-supervisor"
"$D/stock-supervisor"
echo "===== SUPERVISED RAW SESSION E2E ====="
"$CC" "${common[@]}" -DONEIOS_RAW_SOURCE_TEST \
  "$T/test_stock_session_e2e.c" "$S/stock_sample_reader.c" \
  "$S/stock_session_runner.c" "$S/stock_thermal_supervisor.c" \
  "$S/quiesce_supervisor.c" "$S/quiesce.c" "$S/quiesce_runtime.c" \
  "$S/quiesce_board.c" "$S/quiesce_board_runtime.c" "$S/quiesce_board_worker.c" \
  "$S/quiesce_input.c" "$S/quiesce_vcpu.c" \
  "$N/sm8850_stock_session.c" "$N/sm8850_thermal_source.c" \
  "$N/sm8850_thermal_controller.c" -o "$D/e2e"
mkdir -p "$D/raw"
python3 - "$D/raw" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
boot = "51ca8a7b-7fe0-4075-be5f-6a9029b8d392"
def put(rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="ascii")
    p.chmod(0o600)
put("proc/sys/kernel/random/boot_id", boot + "\n")
put("data/adb/oneios-m3q-framework/thermal.guard.manifest",
    f"v1 {boot} 3\nz 2 cpu-1 cpu\nz 3 gpuss-0 gpu\nz 4 ddr ddr\n")
for i, name, temp in [(2,"cpu-1",45000),(3,"gpuss-0",42000),(4,"ddr",40000)]:
    put(f"sys/class/thermal/thermal_zone{i}/type", name + "\n")
    put(f"sys/class/thermal/thermal_zone{i}/temp", str(temp) + "\n")
put("sys/class/power_supply/battery/temp", "300\n")
put("sys/class/power_supply/battery/lrp", "300\n")
put("sys/class/sec/sec-ap-thermistor/temperature", "400\n")
PY
"$D/e2e" "$D/raw"
echo "===== ANDROID NATIVE COMPILE ====="
NDK="${ANDROID_NDK_ROOT:-${NDK:-$HOME/Android/Sdk/ndk/28.2.13676358}}"
AC="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang"
test -x "$AC"
for src in "$S/stock_sample_reader.c" "$S/stock_session_runner.c" \
    "$S/stock_thermal_supervisor.c" "$S/quiesce_supervisor.c" \
    "$S/quiesce_board_worker.c" "$S/quiesce_input.c" "$S/quiesce_vcpu.c" \
    "$N/sm8850_stock_session.c" "$N/sm8850_thermal_source.c"; do
    "$AC" -std=gnu11 -O2 -g -Wall -Wextra -Werror \
      -I"$S" -I"$N" -I"$R/runtime/xnuhost/include" -I"$R/runtime/xnuhost/stub" \
      -I"$R/runtime/loader/include" -I"$R/runtime/bridges/include" \
      -I"$R/runtime/bridges/encoder" -I"$R/drivers/bridge" -I"$R/drivers/camera" \
      -c "$src" -o "$D/$(basename "$src").android.o"
done
echo "ANDROID_NATIVE_COMPILE=PASS"
echo "STOCK_SESSION_INTEGRATION_OFFLINE=PASS"
echo "DEVICE_ACCESS=NONE"
echo "EVIDENCE=$D"
