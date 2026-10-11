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

# Package the app as a ready-to-run disk image: open it, drag "Bumblebee GCS"
# onto Applications, done -- nothing to build on the user's Mac.
#
#   ./make_dmg.sh          # builds the universal app first if needed
# Output: build/BumblebeeGCS-<version>-mac.dmg (+ .sha256)
set -euo pipefail
cd "$(dirname "$0")"

APP="build/Bumblebee GCS.app"
[ -d "$APP" ] || ./build_app.sh
VER=$(/usr/libexec/PlistBuddy -c 'Print CFBundleShortVersionString' "$APP/Contents/Info.plist")
OUT="build/BumblebeeGCS-$VER-mac.dmg"

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/Как открыть - How to open.txt" <<'EOF'
Bumblebee GCS для Mac (Apple Silicon и Intel, macOS 14 и новее)

1. Перетащите «Bumblebee GCS» на папку «Applications» (Программы).
2. Откройте программу из «Программ». Если macOS пишет, что не может
   проверить разработчика: «Системные настройки» -> «Конфиденциальность и
   безопасность» -> внизу «Всё равно открыть» -> подтвердите. Это нужно
   только один раз.
3. Когда программа спросит про геолокацию, разрешите: без этого macOS не
   показывает программам названия Wi-Fi сетей, и новые дроны не видны.

Bumblebee GCS for Mac (Apple Silicon and Intel, macOS 14 or later)

1. Drag "Bumblebee GCS" onto the Applications folder.
2. Open it from Applications. If macOS says it cannot verify the developer:
   System Settings -> Privacy & Security -> "Open Anyway" at the bottom ->
   confirm. Needed once.
3. Allow Location Services when asked: macOS only shows WiFi names to apps
   that have it, and new drones are found by their WiFi name.
EOF

rm -f "$OUT" "$OUT.sha256"
hdiutil create -quiet -volname "Bumblebee GCS $VER" -srcfolder "$STAGE" -fs HFS+ -format UDZO "$OUT"
(cd build && shasum -a 256 "$(basename "$OUT")" > "$(basename "$OUT").sha256")
echo "==> $OUT ($(du -h "$OUT" | cut -f1))"
cat "$OUT.sha256"
