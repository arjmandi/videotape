#!/usr/bin/env bash
# Builds TapePlayer in Release and leaves it at clients/macos/build/TapePlayer.app.
set -euo pipefail
cd "$(dirname "$0")"
xcodebuild build -quiet -project TapePlayer.xcodeproj -scheme TapePlayer -configuration Release \
  -destination "platform=macOS,arch=$(uname -m)" -derivedDataPath build/DerivedData
rm -rf build/TapePlayer.app
ditto build/DerivedData/Build/Products/Release/TapePlayer.app build/TapePlayer.app
echo "built $(pwd)/build/TapePlayer.app"
