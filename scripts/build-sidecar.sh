#!/usr/bin/env bash
# Packages the Python backend into a single executable that the desktop app ships as a
# Tauri "sidecar". Tauri requires the file name to end in the Rust target triple.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TRIPLE="${TARGET_TRIPLE:-$(rustc --print host-tuple)}"
OUT="$ROOT/desktop/src-tauri/binaries"

cd "$ROOT/backend"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -e . "pyinstaller>=6.10"

EXTRA=()
if [ "$(uname)" = "Darwin" ] && [ -n "${APPLE_SIGNING_IDENTITY:-}" ]; then
  # Sign the Python libraries inside the one-file binary with the app's identity, so the
  # hardened runtime lets the engine load them after it unpacks itself at launch.
  EXTRA+=(--codesign-identity "$APPLE_SIGNING_IDENTITY"
          --osx-entitlements-file "$ROOT/desktop/src-tauri/Entitlements.plist")
fi

.venv/bin/pyinstaller run_server.py \
  --name brief-api \
  --onefile \
  --noconfirm \
  --clean \
  --log-level WARN \
  --distpath build/dist \
  --workpath build/work \
  --specpath build \
  --collect-submodules uvicorn \
  --collect-submodules app \
  ${EXTRA[@]+"${EXTRA[@]}"}  # bash 3.2 (macOS) treats an empty "${EXTRA[@]}" as unbound

mkdir -p "$OUT"
cp build/dist/brief-api "$OUT/brief-api-$TRIPLE"
echo "Sidecar ready: $OUT/brief-api-$TRIPLE"
