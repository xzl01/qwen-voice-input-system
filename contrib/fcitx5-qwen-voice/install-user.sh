#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BUILD_DIR="$SCRIPT_DIR/build"
PREFIX="${XDG_DATA_HOME:-$HOME/.local}"

cmake -S "$SCRIPT_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX"
cmake --build "$BUILD_DIR"
cmake --install "$BUILD_DIR"

CONF="$PREFIX/share/fcitx5/addon/qwenvoicefcitx5.conf"
LIB="$PREFIX/lib/fcitx5/libqwenvoicefcitx5.so"

if [[ -f "$CONF" && -f "$LIB" ]]; then
  python - "$CONF" "$LIB" <<'PY'
from pathlib import Path
import sys

conf = Path(sys.argv[1])
lib = Path(sys.argv[2]).resolve()
lines = conf.read_text(encoding="utf-8").splitlines()
updated = []
for line in lines:
    if line.startswith("Library="):
        updated.append(f"Library={lib}")
    else:
        updated.append(line)
conf.write_text("\n".join(updated) + "\n", encoding="utf-8")
PY
fi

echo "Installed qwenvoicefcitx5 addon to $PREFIX"
echo "Restart fcitx5 to load the addon."
