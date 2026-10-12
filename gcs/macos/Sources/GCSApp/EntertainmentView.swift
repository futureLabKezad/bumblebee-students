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

struct EntertainmentView: View {
    @EnvironmentObject var app: AppState

    @State private var color: Color = .white
    @State private var activeAnim: String?
    @State private var isOn = true
    @State private var lastState: LEDState = .color(255, 255, 255)
    @State private var colorTask: Task<Void, Never>?

    @State private var customTune = ""
    @State private var customFmt = "QBASIC"
    @State private var soundMsg = ""

    @State private var ttsText = ""
    @State private var ttsLang = "en"
    @State private var ttsOut = ""

    enum LEDState { case color(Int, Int, Int); case anim(String); case none }

    private let animations = ["breathing", "rainbow", "police", "strobe", "fire", "theater",
                              "rainbow_theater"]
    // Shows drive the LEDs and a looping PX4 buzzer melody from one process on
    // the drone. Same /api/led/animation endpoint -- only one can run at a time,
    // which is why they share `activeAnim` with the plain animations above.
    private let shows = ["party", "siren", "alarm", "victory"]
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
    }

    private var ledPanel: some View {
        Panel(title: "LED Color", icon: "paintpalette") {
            ColorPicker("Color", selection: $color, supportsOpacity: false)
                .onChange(of: color) { _, _ in scheduleColor() }
            HStack {
                Text(hexString).font(Theme.mono).foregroundStyle(Theme.muted)
                Spacer()
                Button(isOn ? "Off" : "On") { toggleOnOff() }.buttonStyle(GhostButtonStyle())
                Button("Reset") { run { try await app.api.ledReset(); activeAnim = nil; lastState = .none } }
                    .buttonStyle(GhostButtonStyle())
            }
        }
    }

    private var animPanel: some View {
        Panel(title: "Animations", icon: "sparkles") {
            animGrid(animations)
        }
    }

    private var showsPanel: some View {
        Panel(title: "Shows (Light + Sound)", icon: "music.note.list") {
            animGrid(shows, sound: true)
        }
    }

    private func animGrid(_ names: [String], sound: Bool = false) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 100), spacing: Theme.s2)], spacing: Theme.s2) {
            ForEach(names, id: \.self) { name in
                ChipButton(label: label(name),
                           icon: icons[name] ?? "sparkles",
                           selected: activeAnim == name,
                           fullWidth: true,
                           badge: sound ? "speaker.wave.2.fill" : nil) {
                    run {
                        try await app.api.ledAnimation(name)
                        activeAnim = name; lastState = .anim(name); isOn = true
                    }
                }
            }
        }
    }

    private var soundsPanel: some View {
        Panel(title: "Buzzer", icon: "speaker.wave.2.fill") {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 80), spacing: Theme.s2)], spacing: Theme.s2) {
                ForEach(presets, id: \.0) { (name, tune, fmt) in
                    Button(name) { run { _ = try await app.api.playTune(tune, format: fmt); soundMsg = "played \(name)" } }
                        .buttonStyle(GhostButtonStyle())
                        .frame(maxWidth: .infinity)
                }
            }
            GlassTextField(placeholder: "Custom tune", text: $customTune)
            HStack {
                SegmentedTabs(options: [("QBASIC", "QBASIC"), ("MML", "MML")], selection: $customFmt)
                Button("Play Tune") {
                    run { let r = try await app.api.playTune(customTune, format: customFmt)
                          soundMsg = (r["error"] as? String) ?? "played" }
                }.buttonStyle(AccentButtonStyle()).disabled(customTune.isEmpty)
                Spacer()
            }
            if !soundMsg.isEmpty { StatusBanner(text: soundMsg, kind: soundMsg.hasPrefix("error") ? .error : .success) }
        }
    }

    private var ttsPanel: some View {
        Panel(title: "Speech (TTS)", icon: "text.bubble") {
            GlassTextField(placeholder: "Text to speak", text: $ttsText)
            SegmentedTabs(options: languages.map { (label: $0.uppercased(), value: $0) }, selection: $ttsLang)
            HStack {
                Button("Speak") {
                    run { let r = try await app.api.tts(text: ttsText, lang: ttsLang)
                          let tune = (r["tune"] as? String) ?? ""
                          let ph = (r["phonemes"] as? String).map { " · \($0)" } ?? ""
                          ttsOut = String((tune + ph).prefix(230)) }
                }.buttonStyle(AccentButtonStyle()).disabled(ttsText.isEmpty)
                Spacer()
            }
            if !ttsOut.isEmpty { StatusBanner(text: ttsOut, kind: .info) }
        }
    }

    // MARK: - Helpers

    /// Drone-side animation names are lowercase single tokens ("rainbow_theater").
    private func label(_ name: String) -> String {
        name.replacingOccurrences(of: "_", with: " ").capitalized
    }

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
            try? await app.api.ledColor(r: r, g: g, b: b)
            await MainActor.run { activeAnim = nil; lastState = .color(r, g, b); isOn = true }
        }
    }

    private func toggleOnOff() {
        if isOn {
            run { try await app.api.ledColor(r: 0, g: 0, b: 0); isOn = false }
        } else {
            isOn = true
            switch lastState {
            case .anim(let n): run { try await app.api.ledAnimation(n) }
            case .color(let r, let g, let b): run { try await app.api.ledColor(r: r, g: g, b: b) }
            case .none: run { try await app.api.ledReset() }
            }
        }
    }

    private func run(_ op: @escaping () async throws -> Void) {
        Task {
            do { try await op() }
            catch { await MainActor.run { soundMsg = "error: \(error.localizedDescription)" } }
        }
    }
}
