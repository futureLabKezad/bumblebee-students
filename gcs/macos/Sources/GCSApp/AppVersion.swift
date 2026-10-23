// Copyright 2026 FutureLab
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import Foundation

/// The app version shown on screen, so a teacher can tell which build a laptop
/// runs. Comes from Info.plist (gcs/VERSION is the source; check_versions.py
/// keeps them equal). "dev" when run outside the app bundle (`swift run`).
enum AppVersion {
    static let short: String =
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "dev"
    static let label = "GCS " + short
    static let build: String = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "dev"
}
