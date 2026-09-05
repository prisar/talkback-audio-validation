#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$ROOT/talkback-validator"
APP="$ROOT/talkback-demo-app"
ARTIFACTS="$ROOT/artifacts"

MODE="live"
[ "${1:-}" = "--replay" ] && MODE="replay"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

need() {
  command -v "$1" >/dev/null 2>&1 || die "$2"
}

say "Checking prerequisites"
need uv "uv is not installed. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
echo "uv           $(uv --version)"

cd "$VALIDATOR"

say "Installing Python dependencies"
if [ "$MODE" = "replay" ]; then
  uv sync --quiet
else
  uv sync --quiet --extra cloud --extra capture --extra ocr
fi

say "Running the test suite"
uv run --with pytest pytest -q

if [ "$MODE" = "replay" ]; then
  say "Replaying committed fixtures (no device, no API key)"
  uv run talkback-validator replay fixtures --out runs/replay
  REPORT="$VALIDATOR/runs/replay/index.html"
else
  say "Checking system tools"
  if ! command -v tesseract >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
      echo "installing tesseract and portaudio via brew"
      brew install tesseract portaudio
    else
      die "tesseract is required for OCR. Install Homebrew, or run with --replay."
    fi
  fi
  need adb "adb not found. Install Android platform-tools and add it to PATH."

  if [ -z "$(adb devices | sed -n '2p')" ]; then
    die "No Android device connected. Enable USB debugging, or run: ./run-demo.sh --replay"
  fi

  if [ ! -f "$ARTIFACTS/aidsim.apk" ]; then
    say "Building the AidSim fixture APK"
    [ -d "$APP" ] || die "No APK in artifacts/ and no app source to build it from."
    (cd "$APP" && ./gradlew assembleDebug -q)
    cp "$APP/app/build/outputs/apk/debug/app-debug.apk" "$ARTIFACTS/aidsim.apk"
  fi

  say "Preflight checks"
  uv run talkback-validator doctor || echo "(doctor reported problems; continuing)"

  say "Live run: correct labels"
  uv run talkback-validator run aidsim --defect none --out runs/live-clean --control

  say "Live run: injected volume_sign defect"
  uv run talkback-validator run aidsim --defect volume_sign --fields right_volume \
    --out runs/live-defect

  REPORT="$VALIDATOR/runs/live-clean/index.html"
fi

say "Report"
echo "$REPORT"
if command -v open >/dev/null 2>&1; then
  open "$REPORT"
fi
