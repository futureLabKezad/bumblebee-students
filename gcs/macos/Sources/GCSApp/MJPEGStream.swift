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

import SwiftUI
import AppKit

/// Native MJPEG (`multipart/x-mixed-replace`) client. Streams from
/// `http://host:8080/stream?...`, splits the byte stream on JPEG SOI/EOI
/// markers, decodes each frame to an NSImage and publishes the latest one.
/// No WebView involved — the video is rendered fully natively.
///
/// One stream object holds at most one connection. Its state lives on the
/// main thread; every connection has its own session and buffer, and its
/// callbacks carry a generation number, so a connection that was replaced
/// (camera tab switched, Disconnect) can neither show a frame nor schedule a
/// retry. The drone's server writes an empty boundary every 5 s, so 10 s
/// without a byte means the connection is dead (drone rebooted): it is
/// dropped and opened again, and the video comes back by itself.
final class MJPEGStream: NSObject, ObservableObject {
    @Published var image: NSImage?
    @Published var receiving = false
    @Published private(set) var lastFrameAt: Date?
    @Published private(set) var startedAt: Date?

    /// Seconds without a byte before the connection counts as dead.
    var idleTimeout: TimeInterval = 10
    static let retryDelay: TimeInterval = 1.2

    private var connection: MJPEGConnection?
    private var currentURL: URL?
    private var generation = 0

    /// `force` reopens the same URL (Reconnect).
    func start(url: URL, force: Bool = false) {
        if !force, url == currentURL, connection != nil { return }
        stop()
        currentURL = url
        image = nil
        lastFrameAt = nil
        startedAt = Date()
        open(url)
    }

    func stop() {
        generation += 1
        connection?.cancel()
        connection = nil
        currentURL = nil
        startedAt = nil
        receiving = false
    }

    private func open(_ url: URL) {
        generation += 1
        let gen = generation
        connection = MJPEGConnection(url: url, idleTimeout: idleTimeout) { [weak self] event in
            DispatchQueue.main.async { self?.handle(event, gen: gen) }
        }
    }

    private func handle(_ event: MJPEGConnection.Event, gen: Int) {
        guard gen == generation else { return }   // a replaced connection
        switch event {
        case .frame(let img):
            image = img
            lastFrameAt = Date()
            receiving = true
        case .ended:
            receiving = false
            connection = nil
            // Auto-retry the same URL after a short delay (server restart / wifi blip).
            guard let url = currentURL else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + Self.retryDelay) { [weak self] in
                guard let self = self, gen == self.generation, self.currentURL == url,
                      self.connection == nil else { return }
                self.open(url)
            }
        }
    }
}

/// One HTTP connection of an MJPEGStream, with its own session and buffer.
private final class MJPEGConnection: NSObject, URLSessionDataDelegate {
    enum Event { case frame(NSImage), ended }

    private var session: URLSession?
    private var buffer = Data()
    private let onEvent: (Event) -> Void

    // JPEG markers.
    private let soi = Data([0xFF, 0xD8])
    private let eoi = Data([0xFF, 0xD9])

    init(url: URL, idleTimeout: TimeInterval, onEvent: @escaping (Event) -> Void) {
        self.onEvent = onEvent
        super.init()
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = idleTimeout       // idle watchdog
        cfg.timeoutIntervalForResource = .infinity
        let queue = OperationQueue()
        queue.maxConcurrentOperationCount = 1             // delegate calls in order, one at a time
        let s = URLSession(configuration: cfg, delegate: self, delegateQueue: queue)
        session = s
        s.dataTask(with: url).resume()
    }

    /// The session keeps its delegate (this object) until invalidated.
    func cancel() {
        session?.invalidateAndCancel()
    }

    // MARK: - URLSessionDataDelegate

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        buffer.append(data)
        extractFrames()
        // Guard against unbounded growth if no full frame appears.
        if buffer.count > 4 * 1024 * 1024 {
            buffer.removeAll(keepingCapacity: true)
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        session.invalidateAndCancel()
        onEvent(.ended)
    }

    // MARK: - Frame extraction

    private func extractFrames() {
        // Consume every complete JPEG in the buffer but keep only the LAST one,
        // then decode it once. If frames arrive in a burst (wifi jitter, a
        // higher fps than the UI redraws), decoding only the freshest frame
        // keeps latency low and avoids wasting CPU on frames that would be
        // immediately overwritten on screen.
        var lastFrame: Data?
        while true {
            guard let start = buffer.range(of: soi) else { break }
            guard let endRange = buffer.range(of: eoi, in: start.upperBound..<buffer.endIndex) else {
                // No complete frame yet; drop any garbage before SOI.
                if start.lowerBound > buffer.startIndex {
                    buffer.removeSubrange(buffer.startIndex..<start.lowerBound)
                }
                break
            }
            lastFrame = buffer.subdata(in: start.lowerBound..<endRange.upperBound)
            buffer.removeSubrange(buffer.startIndex..<endRange.upperBound)
        }
        if let frameData = lastFrame, let img = NSImage(data: frameData) {
            onEvent(.frame(img))
        }
    }
}
