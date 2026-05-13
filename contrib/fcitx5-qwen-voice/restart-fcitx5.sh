#!/usr/bin/env bash
set -euo pipefail

if command -v fcitx5-remote >/dev/null 2>&1; then
  fcitx5-remote -r || true
fi

pkill -x fcitx5 || true
setsid fcitx5 >/dev/null 2>&1 &

echo "fcitx5 restarted"
