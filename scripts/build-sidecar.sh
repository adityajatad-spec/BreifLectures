#!/usr/bin/env bash
# Packages the Python backend into the two executables the desktop app ships as Tauri
# "sidecars" (Tauri requires the file names to end in the Rust target triple):
#   brief-api         the engine: API, web UI, analysis. Small and starts in about a second.
#   brief-transcribe  speech-to-text for lectures without captions (Whisper, yt-dlp, Deno).
#                     Large, so it's separate: it only unpacks when a lecture needs it, and
#                     its memory is freed as soon as it finishes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TRIPLE="${TARGET_TRIPLE:-$(rustc --print host-tuple)}"
OUT="$ROOT/desktop/src-tauri/binaries"

# Windows (Git Bash) puts venv tools in Scripts/ and gives executables a .exe suffix.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) BIN=.venv/Scripts; EXE=.exe; SEP=";"; PY="${PYTHON:-python}" ;;
  *) BIN=.venv/bin; EXE=; SEP=":"; PY="${PYTHON:-python3}" ;;
esac

cd "$ROOT/backend"
[ -d .venv ] || "$PY" -m venv .venv
"$BIN/python" -m pip install -q -e . "pyinstaller>=6.10"

COMMON=(--onefile --noconfirm --clean --log-level WARN
        --distpath build/dist --workpath build/work --specpath build)
if [ "$(uname)" = "Darwin" ] && [ -n "${APPLE_SIGNING_IDENTITY:-}" ]; then
  # Sign the libraries inside each binary with the app's identity, so the hardened runtime
  # lets them load after the binary unpacks itself at launch.
  COMMON+=(--codesign-identity "$APPLE_SIGNING_IDENTITY"
           --osx-entitlements-file "$ROOT/desktop/src-tauri/Entitlements.plist")
fi

# The engine never imports the speech stack; keep it out so the engine stays small and fast.
"$BIN/pyinstaller" run_server.py --name brief-api "${COMMON[@]}" \
  --collect-submodules uvicorn \
  --exclude-module app.transcribe \
  --exclude-module faster_whisper --exclude-module ctranslate2 --exclude-module onnxruntime \
  --exclude-module av --exclude-module yt_dlp --exclude-module numpy

DENO="$("$BIN/python" -c 'import deno; print(deno.find_deno_bin())')"
"$BIN/pyinstaller" run_transcriber.py --name brief-transcribe "${COMMON[@]}" \
  --collect-data faster_whisper \
  --collect-binaries ctranslate2 \
  --collect-data yt_dlp_ejs \
  --add-binary "$DENO${SEP}bin"

mkdir -p "$OUT"
for name in brief-api brief-transcribe; do
  cp "build/dist/$name$EXE" "$OUT/$name-$TRIPLE$EXE"
  echo "Sidecar ready: $OUT/$name-$TRIPLE$EXE ($(du -h "build/dist/$name$EXE" | cut -f1))"
done
