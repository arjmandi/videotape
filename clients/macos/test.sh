#!/usr/bin/env bash
# Runs TapeKit's unit tests, then TapePlayer's UI tests. The UI tests take over the mouse and screen while they run, and
# play examples/contrail/tapes/terminal, so render it first: in examples/contrail, run
# uv run videotape render --story terminal
# With --published <app>, an app videotape publish made, one more test walks a copy of that app. The copy and the clearing
# of the player's caches happen here, because the UI test runner is sandboxed: it can write only in its own container,
# and an app copied there does not launch.
# Arguments after the script go to xcodebuild, such as -resultBundlePath <path>.
set -euo pipefail
if [ "${1:-}" = --published ]; then
  [ -d "${2:-}" ] || { echo "--published needs the path of an app videotape publish made" >&2; exit 2; }
  folder="$(mktemp -d)"
  trap 'rm -rf "$folder"' EXIT
  ditto "$2" "$folder/$(basename "$2")"
  id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$folder/$(basename "$2")/Contents/Info.plist")"
  for kept in "Caches/$id" "Saved Application State/$id.savedState" "HTTPStorages/$id" "HTTPStorages/$id.binarycookies" \
              "WebKit/$id" "Application Support/$id"; do
    rm -rf "${HOME:?}/Library/$kept"
  done
  defaults delete "$id" 2>/dev/null || true
  export TEST_RUNNER_PUBLISHED_APP="$folder/$(basename "$2")"
  shift 2
fi
cd "$(dirname "$0")"
swift test --package-path TapeKit
xcodebuild test -project TapePlayer.xcodeproj -scheme TapePlayer -destination "platform=macOS,arch=$(uname -m)" \
  -derivedDataPath build/DerivedData "$@"
