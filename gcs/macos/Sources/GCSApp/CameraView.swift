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

/// Native MJPEG camera view. Owns an MJPEGStream and rebuilds the URL when the
/// host or topic changes. Supports 180° flip.
///
/// What lies over the picture comes from VideoOverlay: a frame older than 3 s
/// is dimmed under "Video lost"; topics that only publish in flight (ArUco)
/// show their VideoHints text instead of an endless spinner.
struct CameraView: View {
    let host: String
    let topic: String
    var quality = 60
    var fps = 12
    var width = 320
    var height = 240
    var compact = false            // small picture-in-picture: smaller text
    var restartToken = 0           // bump to reopen the stream (Reconnect)
    @State private var flipped = false
    @StateObject private var stream = MJPEGStream()

    private var streamURL: URL? {
        URL(string: "http://\(host):8080/stream?topic=\(topic)&type=mjpeg&quality=\(quality)&fps=\(fps)&width=\(width)&height=\(height)")
    }

    var body: some View {
        ZStack {
            Color.black
            TimelineView(.periodic(from: .now, by: 0.5)) { ctx in
                picture(VideoStatus.of(lastFrameAt: stream.lastFrameAt, startedAt: stream.startedAt, now: ctx.date))
            }
            VStack {
                HStack {
                    Spacer()
                    Button { flipped.toggle() } label: {
                        Image(systemName: "arrow.triangle.2.circlepath")
                    }
                    .buttonStyle(.borderless)
                    .padding(Theme.s1 + 2)
                    .background(Theme.scrim)
                    .clipShape(Circle())
                    .padding(Theme.s1 + 2)
                    .help("Flip 180°")
                }
                Spacer()
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: Theme.rMedia))
        .onAppear { restart() }
        .onChange(of: host) { _, _ in restart() }
        .onChange(of: topic) { _, _ in restart() }
        .onChange(of: restartToken) { _, _ in restart(force: true) }
        .onDisappear { stream.stop() }
    }

    @ViewBuilder
    private func picture(_ status: VideoStatus) -> some View {
        let overlay = VideoOverlay.of(status: status, hasImage: stream.image != nil,
                                      idleHint: VideoHints.idleHint(topic: topic))
        if let img = stream.image {
            let lost: Bool = { if case .lost = overlay { return true } else { return false } }()
            ZStack {
                Image(nsImage: img)
                    .resizable()
                    .interpolation(.medium)
                    .aspectRatio(contentMode: .fit)
                    .rotationEffect(.degrees(flipped ? 180 : 0))
                    .opacity(lost ? 0.35 : 1)
                    .saturation(lost ? 0 : 1)
                if case .lost(let s, let hint) = overlay {
                    VStack(spacing: Theme.s1) {
                        Label("Video lost", systemImage: "video.slash")
                            .font(compact ? Theme.micro : Theme.bodyStrong)
                        Text("\(s) s").font(compact ? Theme.micro : Theme.monoSmall)
                        if let hint, !compact {
                            Text(hint).font(Theme.monoSmall).multilineTextAlignment(.center)
                        }
                    }
                    .foregroundStyle(Theme.text)
                    .padding(compact ? Theme.s1 : Theme.s3)
                    .background(Theme.scrim, in: RoundedRectangle(cornerRadius: Theme.rControl))
                }
            }
        } else if case .hint(let hint) = overlay {
            Text(hint)
                .font(compact ? Theme.micro : Theme.monoSmall)
                .foregroundStyle(Theme.muted)
                .multilineTextAlignment(.center)
                .padding(compact ? Theme.s1 : Theme.s4)
        } else {
            VStack(spacing: Theme.s2) {
                ProgressView().controlSize(.small)
                Text("waiting for video…").font(compact ? Theme.micro : Theme.monoSmall).foregroundStyle(Theme.muted)
            }
        }
    }

    private func restart(force: Bool = false) {
        guard let url = streamURL else { return }
        stream.start(url: url, force: force)
    }
}
