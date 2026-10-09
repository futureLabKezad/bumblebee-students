#!/bin/bash
# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Build the Bumblebee GCS native macOS app and assemble it into a .app bundle.
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="Bumblebee GCS"
CONFIG="${1:-release}"

echo "==> swift build ($CONFIG)"
swift build -c "$CONFIG"
BIN_DIR="$(swift build -c "$CONFIG" --show-bin-path)"
BIN="$BIN_DIR/GCSApp"

APP="build/${APP_NAME}.app"
echo "==> assembling $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/GCSApp"
cp Info.plist "$APP/Contents/Info.plist"

# Bundle the SwiftPM resource bundle (AppIcon.png etc.) so Bundle.module resolves
# at runtime, and place the .icns for the Finder/Dock icon.
for b in "$BIN_DIR"/*.bundle; do
  [ -e "$b" ] && cp -R "$b" "$APP/Contents/Resources/"
done
cp Sources/GCSApp/Resources/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

# Ad-hoc sign so it launches without a quarantine/Gatekeeper hard stop. The
# designated requirement names only the bundle id, so macOS keeps the app's
# Location / Local Network permissions across rebuilds (a plain ad-hoc
# signature is tied to the exact binary and every rebuild looks like a new app).
codesign --force --deep --sign - \
    --requirements '=designated => identifier "com.bumblebee.gcs"' "$APP" >/dev/null 2>&1 || true

echo "==> done: $APP"
echo "    run with:  open \"$APP\"   (or: \"$APP/Contents/MacOS/GCSApp\")"
