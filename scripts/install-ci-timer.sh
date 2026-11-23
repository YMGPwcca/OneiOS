#!/usr/bin/env bash
# Install standalone OneiOS CI as a user-level systemd timer. No root needed.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
case "$ROOT" in
  *' '*|*$'\n'*) echo 'install-ci-timer: path with whitespace is unsupported' >&2; exit 1 ;;
esac
command -v systemctl >/dev/null || { echo 'install-ci-timer: systemctl missing' >&2; exit 1; }
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir"
cat > "$unit_dir/oneios-local-ci.service" <<UNIT
[Unit]
Description=OneiOS standalone CachyOS local CI (no GitHub Actions)

[Service]
Type=oneshot
WorkingDirectory=$ROOT
ExecStart=$ROOT/scripts/ci-watch.sh once
UNIT
cat > "$unit_dir/oneios-local-ci.timer" <<'UNIT'
[Unit]
Description=Poll the trusted OneiOS branch for new commits every minute

[Timer]
OnStartupSec=20s
OnUnitInactiveSec=60s
Unit=oneios-local-ci.service

[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now oneios-local-ci.timer
printf '%s\n' 'Standalone OneiOS CI timer enabled.' \
  'To run immediately: systemctl --user start oneios-local-ci.service' \
  'To see status: scripts/ci-watch.sh status' \
  'To see logs: journalctl --user -u oneios-local-ci.service -f'
