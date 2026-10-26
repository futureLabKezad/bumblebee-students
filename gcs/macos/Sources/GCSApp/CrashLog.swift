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

/// Where crashes of the app are recorded, for "Copy diagnostics".
///
/// An uncaught Objective-C exception is appended to
/// ~/Library/Logs/BumblebeeGCS/crash.log. A Swift crash (fatalError, an index
/// out of range) is a signal: macOS writes its own report to
/// ~/Library/Logs/DiagnosticReports/GCSApp-*.ips, and that one is read back.
enum CrashLog {
    static let dir = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Logs/BumblebeeGCS", isDirectory: true)
    static let file = dir.appendingPathComponent("crash.log")
    static let systemReports = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Logs/DiagnosticReports", isDirectory: true)
    /// The log keeps its newest part only.
    static let maxBytes = 256 * 1024

    static func install() {
        NSSetUncaughtExceptionHandler { e in
            CrashLog.append("""
                \(ISO8601DateFormatter().string(from: Date())) \(AppVersion.label) uncaught exception \(e.name.rawValue): \(e.reason ?? "")
                \(e.callStackSymbols.prefix(25).joined(separator: "\n"))

                """)
        }
    }

    static func append(_ text: String) {
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        var data = (try? Data(contentsOf: file)) ?? Data()
        data.append(Data(text.utf8))
        if data.count > maxBytes { data = data.suffix(maxBytes) }
        try? data.write(to: file, options: .atomic)
    }

    /// The newest crash, in one line: the app's own log or macOS's report.
    static func last() -> String? {
        var newest: (date: Date, text: String)?
        if let attrs = try? FileManager.default.attributesOfItem(atPath: file.path),
           let date = attrs[.modificationDate] as? Date,
           let text = try? String(contentsOf: file, encoding: .utf8),
           let line = lastEntryHeader(text) {
            newest = (date, line + " (\(file.path))")
        }
        let reports = (try? FileManager.default.contentsOfDirectory(
            at: systemReports, includingPropertiesForKeys: [.contentModificationDateKey])) ?? []
        for url in reports where url.lastPathComponent.hasPrefix("GCSApp") {
            guard let date = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate,
                  newest.map({ date > $0.date }) ?? true else { continue }
            newest = (date, "macOS crash report \(url.lastPathComponent) (\(url.path))")
        }
        guard let n = newest else { return nil }
        return "\(ISO8601DateFormatter().string(from: n.date)) · \(n.text)"
    }

    /// The first line of the last entry (entries start with an ISO date).
    static func lastEntryHeader(_ log: String) -> String? {
        log.split(separator: "\n").last { $0.first?.isNumber == true && $0.contains(" uncaught ") }.map(String.init)
    }
}
