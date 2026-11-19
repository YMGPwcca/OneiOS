#!/bin/bash
# The image tests: generated stand-in files only, no Apple files, no network.  scripts/image/tests/run.sh [-v] [PATTERN]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
args=()
for a in "$@"; do case "$a" in -v) args+=(-v) ;; *) args+=(-k "$a") ;; esac; done
ROOT=$(cd ../../.. && pwd)
. "$ROOT/scripts/lib/oneios-tool.sh"
oneios_tool "$ROOT"
exec python3 -m unittest -b ${args[@]+"${args[@]}"} test_image test_verify_boot
