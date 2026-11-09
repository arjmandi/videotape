#!/usr/bin/env bash
# Runs TapeKit's unit tests, then TapePlayer's UI test. The UI test takes over the mouse and screen while it runs, and
# plays examples/surf_shop/tape, so render it first: videotape render examples/surf_shop --model stand-in
# Arguments after the script go to xcodebuild, such as -resultBundlePath <path>.
set -euo pipefail
cd "$(dirname "$0")"
swift test --package-path TapeKit
xcodebuild test -project TapePlayer.xcodeproj -scheme TapePlayer -destination "platform=macOS,arch=$(uname -m)" \
  -derivedDataPath build/DerivedData "$@"
