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
  uv sync --quiet --extra bdd
else
  uv sync --quiet --extra cloud --extra capture --extra ocr --extra local --extra bdd
fi

say "Running the test suite"
uv run --with pytest pytest -q

if [ "$MODE" = "replay" ]; then
  say "Replaying committed fixtures (no device, no API key)"
  uv run talkback-validator replay fixtures --out runs/replay
  REPORT="$VALIDATOR/runs/replay/index.html"
else
  need adb "adb not found. Install Android platform-tools and add it to PATH."

  if [ -z "$(adb devices | sed -n '2p')" ]; then
    die "No Android device connected. Enable USB debugging, or run: ./run-demo.sh --replay"
  fi

  # This script installs the APK that ships in artifacts/. It never builds one,
  # so it needs no app source, no Gradle, no Android SDK build tools, and no
  # Appium. If artifacts/aidsim.apk is missing, that is a packaging error to
  # fix at the source, not something to build around here.
  [ -f "$ARTIFACTS/aidsim.apk" ] || die \
    "No APK at artifacts/aidsim.apk. This script installs the shipped APK; it does not build one. To produce it: (cd talkback-demo-app && ./gradlew assembleDebug) then copy app/build/outputs/apk/debug/app-debug.apk here."

  say "Installing the AidSim fixture APK"
  adb install -r "$ARTIFACTS/aidsim.apk"

  say "Preflight checks"
  uv run talkback-validator doctor || echo "(doctor reported problems; continuing)"

  say "Semantics-tree audit (adb only, no microphone or OCR)"
  uv run talkback-validator audit --apk "$ARTIFACTS/aidsim.apk" --defect none \
    || echo "(unexpected finding on the clean baseline; see above)"
  uv run talkback-validator audit --apk "$ARTIFACTS/aidsim.apk" --defect a11y_suite \
    || echo "(findings above are the intentional a11y_suite defects, expected)"

  REPORT=""
  if command -v tesseract >/dev/null 2>&1 || { command -v brew >/dev/null 2>&1 && brew install tesseract portaudio; }; then
    say "Live run: correct labels"
    if uv run talkback-validator run aidsim --apk "$ARTIFACTS/aidsim.apk" \
      --defect none --out runs/live-clean --control; then
      REPORT="$VALIDATOR/runs/live-clean/index.html"
    else
      echo "(live capture failed; a physical device is needed for the mic-through-air"
      echo "path, an emulator has no real microphone loopback. adb-only results above"
      echo "still stand.)"
    fi

    say "Live run: injected volume_sign defect"
    uv run talkback-validator run aidsim --apk "$ARTIFACTS/aidsim.apk" \
      --defect volume_sign --fields right_volume --out runs/live-defect \
      || echo "(live capture failed; see note above)"
  else
    echo "tesseract unavailable and no Homebrew to install it: skipping the audio-capture"
    echo "scenarios. The adb-only audit above still ran to completion."
  fi
fi

if [ -n "$REPORT" ]; then
  say "Report"
  echo "$REPORT"
  # Served rather than opened from disk: the report's re-run controls post back
  # to this server, and a file:// page can only be read.
  echo "Serving the dashboard. Use its Re-run panel to repeat a field, or Ctrl-C to stop."
  uv run talkback-validator serve-report "$(dirname "$REPORT")"
fi
