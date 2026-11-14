#!/usr/bin/env bash
# Runs TapeKit's unit tests, then TapePlayer's UI tests. The UI tests take over the mouse and screen while they run, and
# play examples/contrail/tapes/terminal, so render it first: in examples/contrail, run
# uv run videotape render --story terminal
# Arguments after the script go to xcodebuild, such as -resultBundlePath <path>.
set -euo pipefail
cd "$(dirname "$0")"
swift test --package-path TapeKit
xcodebuild test -project TapePlayer.xcodeproj -scheme TapePlayer -destination "platform=macOS,arch=$(uname -m)" \
  -derivedDataPath build/DerivedData "$@"
