// swift-tools-version:5.9
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

import PackageDescription

// Native macOS app: a WKWebView shell that hosts the Bumblebee GCS frontend
// locally and connects to a drone selected from a network scan. No third-party
// dependencies on purpose — the Mac is usually on the drone's wifi hotspot with
// no internet, so SwiftPM cannot fetch remote packages.
//
// GCSAppTests covers the screen's decision logic (link state, freshness, armed,
// battery text, log, chart span...) with XCTest: `swift test`.
let package = Package(
    name: "GCSApp",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "GCSApp",
            path: "Sources/GCSApp",
            resources: [.process("Resources")]
        ),
        .testTarget(
            name: "GCSAppTests",
            dependencies: ["GCSApp"],
            path: "Tests/GCSAppTests"
        )
    ]
)
