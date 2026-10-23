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

/// LEDs, shows, buzzer and speech. What runs on the drone comes from
/// GET /api/led/status (polled while this screen is open), not from what this
/// screen last sent: switching sections, another laptop or the drone's own
/// 2-minute limit all show up here. Decisions in EntertainmentLogic.swift.
struct EntertainmentView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var telemetry: TelemetryStore

    @State private var color: Color = .white
    @State private var isOn = true
    @State private var lastState: LEDState = .color(255, 255, 255)
    @State private var colorTask: Task<Void, Never>?
    @State private var led: DroneAPI.LedStatus?
    @State private var ledMsg: (text: String, kind: StatusBanner.Kind)?

    @State private var customTune = ""
    @State private var customFmt = "QBASIC"
    @State private var soundMsg: (text: String, kind: StatusBanner.Kind)?

    @State private var ttsText = ""
    @State private var ttsLang = "en"
    @State private var ttsOut: (text: String, kind: StatusBanner.Kind)?

    enum LEDState { case color(Int, Int, Int); case anim(String); case none }

    /// Each glyph describes what the strips actually do, so the grid is scannable
    /// without reading. Police and Siren share the beacon deliberately — outline
    /// for the silent one, filled for the show that adds the wail.
    private let icons: [String: String] = [
        "breathing":       "lungs.fill",
        "rainbow":         "rainbow",
        "police":          "light.beacon.max",
        "strobe":          "bolt.fill",
        "fire":            "flame.fill",
        "theater":         "sparkles",
        "rainbow_theater": "wand.and.stars",
        "party":           "party.popper.fill",
        "siren":           "light.beacon.max.fill",
        "alarm":           "bell.fill",
        "victory":         "trophy.fill",
    ]
    private let presets: [(String, String, String)] = [
        ("beep", "MFT100L16O5C", "QBASIC"),
        ("ok", "MFT180L8O5CEG", "QBASIC"),
        ("error", "MFT180L8O5GEC<G", "QBASIC"),
        ("notify", "MFT180L8O5E4C4", "QBASIC"),
        ("arming", "MFT180L8O4G4O5C4", "QBASIC"),
        ("imperial", "MFT120L4O4GGGL8E<L16B>L4GL8E<L16B>L2G", "QBASIC"),
        ("mario", "MFT200L8O5EEP8EP8CEP8GP8P4<GP4", "QBASIC"),
        ("tetris", "MFT160L4O5EL8BL8>CL4DL8>CL8<BL4AL8AL8>CL4EL8DL8>C", "QBASIC"),
    ]
    private let languages = ["en", "ru", "de", "fr", "es"]

    /// The animation running on the drone now (nil: none, or not known yet).
    private var running: String? { led?.animation }
    private var soundBlocked: String? { SoundGate.blockedReason(armed: telemetry.armed) }

    var body: some View {
        ScrollView {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: Theme.s4)], spacing: Theme.s4) {
                ledPanel
                animPanel
                showsPanel
                soundsPanel
                ttsPanel
            }
            .padding(Theme.s4)
            .frame(maxWidth: 980)
            .frame(maxWidth: .infinity)
        }
        .background(Theme.appGradient)
        .task { await pollLedStatus() }
    }

    // MARK: - Panels

    private var ledPanel: some View {
        Panel(title: "LED Color", icon: "paintpalette") {
            ColorPicker("Color", selection: $color, supportsOpacity: false)
                .onChange(of: color) { _, _ in scheduleColor() }
            HStack {
                Text(hexString).font(Theme.mono).foregroundStyle(Theme.muted)
                Spacer()
                Button(isOn ? "Off" : "On") { toggleOnOff() }.buttonStyle(GhostButtonStyle())
                Button("Reset") { stop() }.buttonStyle(GhostButtonStyle())
                    .help("Stop colours and animations; the drone shows its own status lights again")
            }
            if let m = ledMsg { StatusBanner(text: m.text, kind: m.kind) }
        }
    }

    private var animPanel: some View {
        Panel(title: "Animations", icon: "sparkles", note: runningNote(in: LedCatalog.animations)) {
            animGrid(LedCatalog.animations)
            stopRow(for: LedCatalog.animations)
        }
    }

    private var showsPanel: some View {
        Panel(title: "Shows (Light + Sound)", icon: "music.note.list", note: runningNote(in: LedCatalog.shows)) {
            animGrid(LedCatalog.shows, sound: true)
            stopRow(for: LedCatalog.shows)
        }
    }

    /// "rainbow · stops by itself in 1:45" while one of `names` runs.
    private func runningNote(in names: [String]) -> String? {
        guard let r = running, names.contains(r) else { return nil }
        return [LedCatalog.label(r), LedText.remaining(led?.remaining)].compactMap { $0 }.joined(separator: " · ")
    }

    @ViewBuilder private func stopRow(for names: [String]) -> some View {
        if let r = running, names.contains(r) {
            HStack {
                Button { stop() } label: { Label("Stop \(LedCatalog.label(r))", systemImage: "stop.fill") }
                    .buttonStyle(GhostButtonStyle())
                Spacer()
            }
        }
    }

    private func animGrid(_ names: [String], sound: Bool = false) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 100), spacing: Theme.s2)], spacing: Theme.s2) {
            ForEach(names, id: \.self) { name in
                ChipButton(label: LedCatalog.label(name),
                           icon: icons[name] ?? "sparkles",
                           selected: running == name,
                           fullWidth: true,
                           badge: sound ? "speaker.wave.2.fill" : nil) {
                    // A second click on the running one stops it.
                    if running == name { stop() } else { start(name) }
                }
            }
        }
    }

    private var soundsPanel: some View {
        Panel(title: "Buzzer", icon: "speaker.wave.2.fill") {
            if let why = soundBlocked { StatusBanner(text: why, kind: .caution) }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 80), spacing: Theme.s2)], spacing: Theme.s2) {
                ForEach(presets, id: \.0) { (name, tune, fmt) in
                    Button(name) { play(tune, fmt, label: name) }
                        .buttonStyle(GhostButtonStyle())
                        .frame(maxWidth: .infinity)
                        .disabled(soundBlocked != nil)
                }
            }
            GlassTextField(placeholder: "Custom tune", text: $customTune)
            HStack {
                SegmentedTabs(options: [("QBASIC", "QBASIC"), ("MML", "MML")], selection: $customFmt)
                Button("Play Tune") { play(customTune, customFmt, label: "custom tune") }
                    .buttonStyle(AccentButtonStyle()).disabled(customTune.isEmpty || soundBlocked != nil)
                Spacer()
            }
            if let m = soundMsg { StatusBanner(text: m.text, kind: m.kind) }
        }
    }

    private var ttsPanel: some View {
        Panel(title: "Speech (TTS)", icon: "text.bubble") {
            if let why = soundBlocked { StatusBanner(text: why, kind: .caution) }
            GlassTextField(placeholder: "Text to speak", text: $ttsText)
            SegmentedTabs(options: languages.map { (label: $0.uppercased(), value: $0) }, selection: $ttsLang)
            HStack {
                Button("Speak") { speak() }
                    .buttonStyle(AccentButtonStyle()).disabled(ttsText.isEmpty || soundBlocked != nil)
                Spacer()
            }
            if let m = ttsOut { StatusBanner(text: m.text, kind: m.kind) }
        }
    }

    // MARK: - LED actions

    private func pollLedStatus() async {
        while !Task.isCancelled {
            if let s = try? await app.api.ledStatus() {
                led = s
                if s.animation == nil { app.startedLedAnimation = false }
            }
            try? await Task.sleep(nanoseconds: 2_500_000_000)
        }
    }

    private func start(_ name: String) {
        Task {
            do {
                try await app.api.ledAnimation(name)
                app.startedLedAnimation = true
                lastState = .anim(name); isOn = true
                ledMsg = nil
                led = (try? await app.api.ledStatus()) ?? led
            } catch { ledMsg = (DroneAPI.describe(error), .error) }
        }
    }

    /// Reset: stops any animation or colour; the drone's status lights return.
    private func stop() {
        Task {
            do {
                try await app.api.ledReset()
                app.startedLedAnimation = false
                lastState = .none
                ledMsg = nil
                led = (try? await app.api.ledStatus()) ?? led
            } catch { ledMsg = (DroneAPI.describe(error), .error) }
        }
    }

    /// Drone-side animation names are lowercase single tokens ("rainbow_theater").
    private var rgb: (Int, Int, Int) {
        let ns = NSColor(color).usingColorSpace(.sRGB) ?? .white
        return (Int((ns.redComponent * 255).rounded()),
                Int((ns.greenComponent * 255).rounded()),
                Int((ns.blueComponent * 255).rounded()))
    }
    private var hexString: String {
        let (r, g, b) = rgb
        return String(format: "#%02X%02X%02X", r, g, b)
    }

    private func scheduleColor() {
        colorTask?.cancel()
        let (r, g, b) = rgb
        colorTask = Task {
            try? await Task.sleep(nanoseconds: 120_000_000)
            if Task.isCancelled { return }
            do {
                try await app.api.ledColor(r: r, g: g, b: b)
                // A colour replaces the animation on the drone.
                app.startedLedAnimation = false
                lastState = .color(r, g, b); isOn = true
                ledMsg = nil
                led = (try? await app.api.ledStatus()) ?? led
            } catch {
                ledMsg = (DroneAPI.describe(error), .error)
            }
        }
    }

    private func toggleOnOff() {
        Task {
            do {
                if isOn {
                    try await app.api.ledColor(r: 0, g: 0, b: 0)
                    app.startedLedAnimation = false
                    isOn = false
                } else {
                    switch lastState {
                    case .anim(let n): try await app.api.ledAnimation(n); app.startedLedAnimation = true
                    case .color(let r, let g, let b): try await app.api.ledColor(r: r, g: g, b: b)
                    case .none: try await app.api.ledReset()
                    }
                    isOn = true
                }
                ledMsg = nil
                led = (try? await app.api.ledStatus()) ?? led
            } catch { ledMsg = (DroneAPI.describe(error), .error) }
        }
    }

    // MARK: - Sound actions

    private func play(_ tune: String, _ fmt: String, label: String) {
        Task {
            do {
                try await app.api.playTune(tune, format: fmt)
                soundMsg = (LedText.sent(label), .success)
            } catch { soundMsg = (DroneAPI.describe(error), .error) }
        }
    }

    private func speak() {
        let text = ttsText, lang = ttsLang
        Task {
            do {
                try await app.api.tts(text: text, lang: lang)
                ttsOut = (LedText.sent("\"\(text)\""), .success)
            } catch { ttsOut = (DroneAPI.describe(error), .error) }
        }
    }
}
