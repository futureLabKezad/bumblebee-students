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

// MARK: - Panel

/// Titled card with an SF Symbol header. `note` ("no data 4 s") sits at the
/// right of the header; `dimmed` greys the content of a quiet source.
struct Panel<Content: View>: View {
    let title: String
    var icon: String? = nil
    var note: String? = nil
    var dimmed = false
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.s3) {
            HStack(spacing: Theme.s2) {
                if let icon { Image(systemName: icon).font(.system(size: Theme.iconSm)).foregroundStyle(Theme.muted) }
                Text(title.uppercased())
                    .font(Theme.sectionLbl).tracking(1.1)
                    .foregroundStyle(Theme.muted)
                Spacer(minLength: 0)
                if let note { Text(note).font(Theme.monoSmall).foregroundStyle(Theme.caution) }
            }
            content.staleDimmed(dimmed)
        }
        .padding(Theme.s4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard(Theme.rPanel)
        .cardShadow()
    }
}

/// Right-aligned "no data N s" line for one group inside a panel.
struct StaleNote: View {
    let status: Freshness.Status
    var body: some View {
        if let note = status.note {
            HStack {
                Spacer()
                Text(note).font(Theme.monoSmall).foregroundStyle(Theme.caution)
            }
        }
    }
}

extension View {
    /// Greys out values whose source went quiet (or never spoke).
    func staleDimmed(_ dimmed: Bool) -> some View {
        opacity(dimmed ? 0.4 : 1).saturation(dimmed ? 0 : 1)
    }
}

// MARK: - StatTile (hero row)

struct StatTile: View {
    let label: String
    let value: String
    var icon: String
    var color: Color = Theme.text
    var caption: String? = nil
    var valueColor: Color = Theme.text
    var captionColor: Color = Theme.muted
    var dimmed = false

    var body: some View {
        HStack(spacing: Theme.s3) {
            ZStack {
                RoundedRectangle(cornerRadius: Theme.rControl).fill(color.opacity(0.15))
                Image(systemName: icon).font(.system(size: Theme.iconMd, weight: .semibold)).foregroundStyle(color)
            }
            .frame(width: 34, height: 34)
            VStack(alignment: .leading, spacing: Theme.s0 - 1) {
                Text(label.uppercased()).font(Theme.sectionLbl).tracking(0.8).foregroundStyle(Theme.muted)
                Text(value).font(Theme.statValue).foregroundStyle(valueColor)
                    .lineLimit(1).minimumScaleFactor(0.6)
                if let caption {
                    Text(caption).font(Theme.label).foregroundStyle(captionColor)
                        .lineLimit(1).minimumScaleFactor(0.8)
                }
            }
            Spacer(minLength: 0)
        }
        .staleDimmed(dimmed)
        .padding(.horizontal, Theme.s3).padding(.vertical, Theme.s2 + 2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard(Theme.rPanel)
    }
}

// MARK: - Alarm banner

/// Persistent red strip for a safety alarm (FC link lost, low battery). Stays
/// until the condition clears; not dismissable.
struct AlarmBanner: View {
    let text: String
    var icon = "exclamationmark.triangle.fill"

    var body: some View {
        HStack(spacing: Theme.s2) {
            Image(systemName: icon).font(.system(size: Theme.iconMd, weight: .semibold))
            Text(text).font(Theme.bodyStrong)
            Spacer(minLength: 0)
        }
        .foregroundStyle(.white)
        .padding(.horizontal, Theme.s4).padding(.vertical, Theme.s2 + 2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.danger)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Status dot

struct StatusDot: View {
    let color: Color
    var pulsing = false
    @State private var on = false
    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 8, height: 8)
            .overlay(Circle().stroke(color.opacity(0.35), lineWidth: on ? 6 : 0))
            .animation(pulsing ? .easeInOut(duration: 1).repeatForever(autoreverses: true) : .default, value: on)
            .onAppear { if pulsing { on = true } }
    }
}

// MARK: - Readouts & bars

struct Readout: View {
    let label: String
    let value: String
    var color: Color = Theme.text
    var body: some View {
        HStack {
            Text(label).font(Theme.monoSmall).foregroundStyle(Theme.muted)
            Spacer()
            Text(value).font(Theme.value).foregroundStyle(color)
        }
    }
}

struct LabeledBar: View {
    let label: String
    let value: String
    let pct: Double
    var color: Color = Theme.primary

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.s1) {
            HStack {
                Text(label).font(Theme.monoSmall).foregroundStyle(Theme.muted)
                Spacer()
                Text(value).font(Theme.monoSmall).foregroundStyle(Theme.text)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.hairline)
                    Capsule().fill(color)
                        .frame(width: geo.size.width * CGFloat(max(0, min(100, pct)) / 100))
                }
            }
            .frame(height: 6)
        }
    }
}

struct Badge: View {
    let text: String
    let color: Color
    var body: some View {
        Text(text)
            .font(Theme.badge)
            .padding(.horizontal, Theme.s2).padding(.vertical, Theme.s1 - 1)
            .background(color.opacity(0.16))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

// MARK: - Drone card (launch screen)

struct DroneCard: View {
    let name: String
    let ip: String
    var reachable = true
    var isLast = false
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: Theme.s3) {
                StatusDot(color: reachable ? Theme.ok : Theme.muted)
                VStack(alignment: .leading, spacing: Theme.s0) {
                    HStack(spacing: Theme.s1 + 2) {
                        Text(name).font(Theme.bodyStrong).foregroundStyle(Theme.text)
                        if isLast { Badge(text: "LAST", color: Theme.caution) }
                    }
                    Text("\(ip)  ·  rosbridge :9090").font(Theme.monoSmall).foregroundStyle(Theme.muted)
                }
                Spacer()
                Text("Connect").font(Theme.bodyMed).foregroundStyle(Theme.primary)
                Image(systemName: "chevron.right").font(.system(size: Theme.iconSm, weight: .semibold)).foregroundStyle(Theme.muted)
            }
            .padding(.horizontal, Theme.s4).padding(.vertical, Theme.s3)
            .background(hover ? Theme.hoverBg : .clear, in: RoundedRectangle(cornerRadius: Theme.rControl))
            .glassCard(Theme.rControl)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }
}

// MARK: - Button styles

struct AccentButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.button)
            .padding(.horizontal, Theme.s4).padding(.vertical, Theme.s2 + 1)
            .background(Theme.primary.opacity(configuration.isPressed ? 0.7 : 1))
            .foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: Theme.rControl))
    }
}

struct GhostButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.buttonSm)
            .padding(.horizontal, Theme.s3).padding(.vertical, Theme.s2)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: Theme.rControl))
            .foregroundStyle(Theme.text)
            .overlay(RoundedRectangle(cornerRadius: Theme.rControl).stroke(Theme.ghostStroke, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: Theme.rControl))
            .opacity(configuration.isPressed ? 0.7 : 1)
            .contentShape(Rectangle())
    }
}

func pctOf(_ v: Double, _ max: Double) -> Double { min(100, abs(v) / max * 100) }

// MARK: - Glass input field

/// The single frosted text-input look used app-wide (replaces stock
/// `.roundedBorder`). Optional leading SF Symbol and a secure variant.
struct GlassTextField: View {
    let placeholder: String
    @Binding var text: String
    var icon: String? = nil
    var secure = false
    var onSubmit: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: Theme.s2) {
            if let icon { Image(systemName: icon).foregroundStyle(Theme.muted) }
            Group {
                if secure {
                    SecureField(placeholder, text: $text)
                } else {
                    TextField(placeholder, text: $text)
                }
            }
            .textFieldStyle(.plain)
            .font(Theme.value)
            .onSubmit { onSubmit?() }
        }
        .padding(.horizontal, Theme.s3).padding(.vertical, Theme.s2 + 1)
        .glassCard(Theme.rControl)
    }
}

extension View {
    /// Wrap an arbitrary control in the glass-field chrome (e.g. a menu Picker).
    func glassField() -> some View {
        padding(.horizontal, Theme.s3).padding(.vertical, Theme.s2 - 2)
            .glassCard(Theme.rControl)
    }
}

// MARK: - Chip button & segmented tabs

/// Toggle chip — blue when selected, faint when not. Shared by the camera tabs
/// and the LED animation grid.
///
/// Two shapes: text-only (compact, the default — camera tabs, `SegmentedTabs`),
/// or icon-over-label when `icon` is set. `badge` puts a small glyph in the
/// corner, used to mark LED shows that also play a melody.
struct ChipButton: View {
    let label: String
    var icon: String? = nil
    var selected: Bool
    var fullWidth = false
    var badge: String? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Group {
                if let icon {
                    VStack(spacing: Theme.s1) {
                        Image(systemName: icon)
                            .font(.system(size: Theme.iconLg))
                        Text(label)
                            .font(Theme.chip)
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, Theme.s2)
                    .padding(.horizontal, Theme.s1)
                    .overlay(alignment: .topTrailing) { badgeGlyph }
                } else {
                    Text(label)
                        .font(Theme.chip)
                        .frame(maxWidth: fullWidth ? .infinity : nil)
                        .padding(.horizontal, Theme.s3).padding(.vertical, Theme.s1 + 1)
                }
            }
            .background(selected ? Theme.selectionBg : Theme.fillFaint,
                        in: RoundedRectangle(cornerRadius: Theme.rControl))
            .foregroundStyle(selected ? Theme.primary : Theme.muted)
            .contentShape(RoundedRectangle(cornerRadius: Theme.rControl))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(badge == nil ? label : "\(label), with sound")
    }

    @ViewBuilder
    private var badgeGlyph: some View {
        if let badge {
            Image(systemName: badge)
                .font(.system(size: 9, weight: .semibold))
                .foregroundStyle(selected ? Theme.primary.opacity(0.75)
                                          : Theme.muted.opacity(0.55))
                .padding(Theme.s1 + 1)
        }
    }
}

/// A row of `ChipButton`s bound to a selection — a glass-consistent segmented
/// control replacing stock `Picker` for small option sets.
struct SegmentedTabs<T: Hashable>: View {
    let options: [(label: String, value: T)]
    @Binding var selection: T
    var fullWidth = false

    var body: some View {
        HStack(spacing: Theme.s1 + 2) {
            ForEach(options, id: \.value) { opt in
                ChipButton(label: opt.label, selected: selection == opt.value, fullWidth: fullWidth) {
                    selection = opt.value
                }
            }
        }
    }
}

// MARK: - Status banner

/// Shared inline status / toast line replacing ad-hoc per-screen strings.
struct StatusBanner: View {
    enum Kind { case info, success, caution, error }
    let text: String
    var kind: Kind = .info

    private var color: Color {
        switch kind {
        case .info: return Theme.muted
        case .success: return Theme.ok
        case .caution: return Theme.caution
        case .error: return Theme.danger
        }
    }

    var body: some View {
        HStack(spacing: Theme.s2) {
            Image(systemName: icon).font(.system(size: Theme.iconSm)).foregroundStyle(color)
            Text(text).font(Theme.monoSmall).foregroundStyle(color)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Theme.s3).padding(.vertical, Theme.s2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: Theme.rControl))
    }

    private var icon: String {
        switch kind {
        case .info: return "info.circle"
        case .success: return "checkmark.circle"
        case .caution: return "exclamationmark.triangle"
        case .error: return "xmark.octagon"
        }
    }
}

// MARK: - Liquid glass surface

extension View {
    /// Frosted material with a gradient edge highlight (brighter at the top) —
    /// the Liquid Glass look without tinting the content.
    func glassCard(_ radius: CGFloat) -> some View {
        self
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: radius))
            .overlay(
                RoundedRectangle(cornerRadius: radius)
                    .strokeBorder(
                        LinearGradient(colors: [Theme.edgeHi, Theme.edgeLo],
                                       startPoint: .top, endPoint: .bottom),
                        lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: radius))
    }

    /// Uniform card elevation — one shadow depth across every glass surface.
    func cardShadow() -> some View {
        shadow(color: Theme.shadowColor, radius: Theme.shadowRadius, y: Theme.shadowY)
    }
}
