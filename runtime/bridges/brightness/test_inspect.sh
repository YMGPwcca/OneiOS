#!/bin/sh
# Passive backlight inspection regression, no phone and no root.
set -eu

binary=build/host/brightctl
if [ "$#" -ge 1 ]; then binary="$1"; fi
[ -x "$binary" ] || { echo "missing host brightctl: $binary" >&2; exit 1; }
case "$binary" in /*) ;; *) binary="$(pwd)/$binary";; esac

dir=$(mktemp -d)
trap 'chmod -R u+w "$dir" 2>/dev/null || :; rm -rf "$dir"' EXIT HUP INT TERM
mkdir -p "$dir/panel" "$dir/panel0-backlight"
printf '0\n' > "$dir/panel/max_brightness"
printf '0\n' > "$dir/panel/brightness"
printf '0\n' > "$dir/panel/actual_brightness"
printf '12750\n' > "$dir/panel0-backlight/max_brightness"
printf '0\n' > "$dir/panel0-backlight/brightness"
printf '0\n' > "$dir/panel0-backlight/actual_brightness"
chmod 0444 "$dir"/panel/* "$dir"/panel0-backlight/*
before=$(cksum "$dir"/panel/* "$dir"/panel0-backlight/*)
out=$(ONEIOS_BRIGHT_DIR="$dir" "$binary" inspect)
after=$(cksum "$dir"/panel/* "$dir"/panel0-backlight/*)
[ "$before" = "$after" ] || { echo "inspect modified the fake sysfs files" >&2; exit 1; }
printf '%s\n' "$out" | grep -Fq 'node panel: max 0; brightness 0; actual 0; bl_power unavailable; skipped (max=0)'
printf '%s\n' "$out" | grep -Fq 'node panel0-backlight: max 12750; brightness 0; actual 0; bl_power unavailable; selected'
printf '%s\n' "$out" | grep -Fq 'WARNING: selected node brightness is 0'
printf '%s\n' "$out" | grep -Fq 'inspect ok (no state changes)'

# A nonzero native panel is chosen first, with no warning.
chmod u+w "$dir/panel/max_brightness" "$dir/panel/brightness"
printf '255\n' > "$dir/panel/max_brightness"
printf '80\n' > "$dir/panel/brightness"
out=$(ONEIOS_BRIGHT_DIR="$dir" "$binary" inspect)
printf '%s\n' "$out" | grep -Fq 'node panel: max 255; brightness 80; actual 0; bl_power unavailable; selected'
if printf '%s\n' "$out" | grep -Fq 'WARNING:'; then
  echo "nonzero selected brightness unexpectedly warned" >&2
  exit 1
fi

# A directory with only zero-max nodes must not claim success.
# Reset BOTH max values: earlier cases deliberately left panel0-backlight usable.
chmod u+w "$dir/panel0-backlight/max_brightness"
printf '0\n' > "$dir/panel/max_brightness"
printf '0\n' > "$dir/panel0-backlight/max_brightness"
if ONEIOS_BRIGHT_DIR="$dir" "$binary" inspect > "$dir/failed.txt"; then
  echo "inspect accepted all-zero maxima" >&2
  exit 1
fi
grep -Fq 'no usable positive-max backlight node' "$dir/failed.txt"

echo 'brightctl inspect: 3 host cases PASS (read-only)'
