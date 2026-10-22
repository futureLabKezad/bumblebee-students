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

struct DashboardView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var t: TelemetryStore
    @EnvironmentObject var metricsClient: MetricsClient

    @State private var bottomTopic = "/main_camera/image_raw"
    @State private var pipBig = false

    private let bottomTabs: [(String, String)] = [
        ("Bottom", "/main_camera/image_raw"),
        ("ArUco", VideoHints.arucoTopic),
    ]

    var body: some View {
        GeometryReader { geo in
            ScrollView {
                VStack(spacing: Theme.s4) {
                    heroRow
                    if let ev = t.controlEvent { controlEventLine(ev) }
                    cameras
                    masonry(width: geo.size.width)
                }
                .padding(Theme.s4)
            }
            .background(Theme.appGradient)
        }
    }

    /// Packs panels into tight columns (Pinterest-style) so short panels don't
    /// leave big gaps the way a row-aligned grid does.
    private func masonry(width: CGFloat) -> some View {
        let cols = width > 1500 ? 3 : (width > 1040 ? 2 : 1)
        let panels: [AnyView] = [
            AnyView(attitudePanel), AnyView(telemetryPanel), AnyView(flightDataPanel),
            AnyView(systemPanel), AnyView(chartsPanel), AnyView(mapPanel), AnyView(logPanel),
        ]
        var columns = Array(repeating: [AnyView](), count: cols)
        for (i, p) in panels.enumerated() { columns[i % cols].append(p) }
        return HStack(alignment: .top, spacing: Theme.s4) {
            ForEach(0..<cols, id: \.self) { c in
                VStack(spacing: Theme.s4) {
                    ForEach(0..<columns[c].count, id: \.self) { j in columns[c][j] }
                }
            }
        }
    }

    // MARK: - Freshness of each source

    private var stateStatus: Freshness.Status { Freshness.status(t.stateAt, limit: Freshness.state, now: t.now) }
    private var poseStatus: Freshness.Status { Freshness.status(t.poseAt, limit: Freshness.pose, now: t.now) }
    private var velStatus: Freshness.Status { Freshness.status(t.velocityAt, limit: Freshness.velocity, now: t.now) }
    private var imuStatus: Freshness.Status { Freshness.status(t.imuAt, limit: Freshness.imu, now: t.now) }
    private var attStatus: Freshness.Status { Freshness.status(t.attitudeAt, limit: Freshness.imu, now: t.now) }
    private var batStatus: Freshness.Status { Freshness.status(t.batteryAt, limit: Freshness.battery, now: t.now) }
    private var metricsStatus: Freshness.Status { Freshness.status(metricsClient.lastAt, limit: Freshness.metrics, now: t.now) }

    // MARK: - Hero

    private var heroRow: some View {
        let state = stateStatus, pose = poseStatus, bat = batStatus
        let armed = t.armedDisplay
        let battery = BatteryDisplay(t.battery)
        let owner = t.owner
        return LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: Theme.s3)], spacing: Theme.s3) {
            StatTile(label: "Mode", value: ModeText.display(t.mode), icon: "airplane", color: Theme.primary,
                     caption: state.isFresh ? ModeText.explain(t.mode) : state.note,
                     captionColor: state.isFresh ? Theme.muted : Theme.caution, dimmed: !state.isFresh)
            StatTile(label: "State", value: armed.text, icon: armed.icon, color: Theme.color(armed.tone),
                     caption: armed.caption, valueColor: Theme.color(armed.valueTone),
                     captionColor: Theme.color(armed.valueTone))
            StatTile(label: "Battery", value: battery.tileValue, icon: battery.icon, color: Theme.color(battery.tone),
                     caption: bat.isFresh ? battery.tileCaption : bat.note,
                     captionColor: bat.isFresh ? Theme.muted : Theme.caution, dimmed: !bat.isFresh)
            StatTile(label: "Z (local)", value: num(t.posZ, "%.2f m"), icon: "arrow.up.to.line", color: Theme.primary,
                     caption: pose.note, captionColor: Theme.caution, dimmed: !pose.isFresh)
            StatTile(label: "Link", value: t.link.text, icon: t.link.icon, color: Theme.color(t.link.tone),
                     caption: t.link.caption(socketAnswered: t.rosConnected, stateNote: state.note),
                     captionColor: Theme.caution)
            StatTile(label: "Control", value: owner.text, icon: owner.icon, color: Theme.color(owner.tone),
                     caption: owner.caption(armed: t.armed), valueColor: Theme.color(owner.valueTone),
                     captionColor: Theme.caution)
        }
    }

    /// The last change of who is in control, as its own line under the tiles.
    private func controlEventLine(_ ev: ControlEventLine) -> some View {
        HStack(spacing: Theme.s2) {
            Image(systemName: "flag.fill").font(.system(size: Theme.iconSm)).foregroundStyle(Theme.color(t.owner.tone))
            Text(ev.time).font(Theme.monoSmall).foregroundStyle(Theme.muted)
            Text(ev.text).font(Theme.bodyStrong).foregroundStyle(Theme.text)
            if !ev.mode.isEmpty {
                Text(ModeText.explain(ev.mode).map { "\(ev.mode) · \($0)" } ?? ev.mode)
                    .font(Theme.monoSmall).foregroundStyle(Theme.muted)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Theme.s3).padding(.vertical, Theme.s2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard(Theme.rControl)
    }

    // MARK: - Cameras

    private var cameras: some View {
        HStack(alignment: .top, spacing: Theme.s4) {
            cameraCard(title: "Front", tabs: nil) {
                CameraView(host: app.droneHost, topic: "/second_camera/image_raw", restartToken: app.videoEpoch)
                    .aspectRatio(4.0/3.0, contentMode: .fit)
            }
            cameraCard(title: "Bottom", tabs: AnyView(tabBar)) {
                ZStack(alignment: .topTrailing) {
                    CameraView(host: app.droneHost, topic: bottomTopic, restartToken: app.videoEpoch)
                        .aspectRatio(4.0/3.0, contentMode: .fit)
                    CameraView(host: app.droneHost, topic: VideoHints.arucoMapTopic,
                               quality: 50, fps: 3, width: 160, height: 120, compact: true,
                               restartToken: app.videoEpoch)
                        .frame(width: pipBig ? 190 : 120, height: pipBig ? 142 : 90)
                        .overlay(RoundedRectangle(cornerRadius: Theme.rMedia).stroke(Theme.primary.opacity(0.7), lineWidth: 1))
                        .padding(Theme.s2)
                        .onTapGesture { pipBig.toggle() }
                }
            }
        }
    }

    private var tabBar: some View {
        SegmentedTabs(options: bottomTabs.map { (label: $0.0, value: $0.1) }, selection: $bottomTopic)
    }

    private func cameraCard<V: View>(title: String, tabs: AnyView?, @ViewBuilder _ content: () -> V) -> some View {
        VStack(alignment: .leading, spacing: Theme.s2) {
            HStack {
                Text(title.uppercased()).font(Theme.sectionLbl).tracking(1.1).foregroundStyle(Theme.muted)
                Spacer()
                if let tabs { tabs }
            }
            content()
                .frame(maxWidth: .infinity)
                .background(Color.black)
                .clipShape(RoundedRectangle(cornerRadius: Theme.rMedia))
        }
        .padding(Theme.s3)
        .frame(maxWidth: .infinity)
        .glassCard(Theme.rPanel)
    }

    // MARK: - Panels

    private var attitudePanel: some View {
        let att = attStatus
        return Panel(title: "Attitude", icon: "gyroscope", note: att.note, dimmed: !att.isFresh) {
            HStack { Spacer(); AttitudeView(roll: t.roll, pitch: t.pitch); Spacer() }
            HStack {
                Readout(label: "Roll", value: num(t.roll, "%.1f°"))
                Readout(label: "Pitch", value: num(t.pitch, "%.1f°"))
                Readout(label: "Yaw", value: num(t.yaw, "%.1f°"))
            }
            Text("Pitch + = nose down (ROS)").font(Theme.monoSmall).foregroundStyle(Theme.muted)
        }
    }

    private var telemetryPanel: some View {
        let battery = BatteryDisplay(t.battery)
        return Panel(title: "Telemetry", icon: "location.fill") {
            group(batStatus) {
                LabeledBar(label: "Battery", value: battery.barText, pct: battery.barPercent, color: Theme.color(battery.tone))
            }
            group(poseStatus) {
                Readout(label: "X", value: num(t.posX, "%+.3f m"), color: Theme.danger)
                Readout(label: "Y", value: num(t.posY, "%+.3f m"), color: Theme.ok)
                Readout(label: "Z (local)", value: num(t.posZ, "%+.3f m"), color: Theme.accent2)
            }
            Divider().overlay(Theme.hairline)
            group(velStatus) {
                Readout(label: "Vx", value: num(t.vx, "%+.3f m/s"))
                Readout(label: "Vy", value: num(t.vy, "%+.3f m/s"))
                Readout(label: "Vz", value: num(t.vz, "%+.3f m/s"))
            }
        }
    }

    private var flightDataPanel: some View {
        Panel(title: "Flight Data", icon: "speedometer") {
            group(velStatus) {
                LabeledBar(label: "Horiz. Speed", value: num(t.speedH, "%.2f m/s"), pct: pctOf(t.speedH ?? 0, 5), color: Theme.dataTeal)
                LabeledBar(label: "Vert. Speed", value: num(t.speedV, "%.2f m/s"), pct: pctOf(t.speedV ?? 0, 3), color: Theme.dataBlue)
            }
            group(imuStatus) {
                LabeledBar(label: "Angular Rate", value: num(t.gyroMag, "%.1f °/s"), pct: pctOf(t.gyroMag ?? 0, 360), color: Theme.dataOrange)
                LabeledBar(label: "IMU Accel", value: num(t.accelMag, "%.2f m/s²"), pct: pctOf(t.accelMag ?? 0, 30), color: Theme.dataGreen)
            }
        }
    }

    private var systemPanel: some View {
        let m = metricsClient.metrics
        let ms = metricsStatus
        return Panel(title: "Raspberry Pi", icon: "cpu", note: ms.note, dimmed: !ms.isFresh) {
            LabeledBar(label: "CPU Temp", value: m.cpuTemp.map { String(format: "%.1f °C", $0) } ?? "—",
                       pct: min(100, m.cpuTemp ?? 0), color: tempColor(m.cpuTemp))
            LabeledBar(label: "CPU Load", value: m.cpuPct.map { String(format: "%.0f%%", $0) } ?? "—",
                       pct: m.cpuPct ?? 0, color: cpuColor(m.cpuPct))
            LabeledBar(label: "Load 1/5/15", value: loadText(m),
                       pct: (m.load1 ?? 0) / Double(m.cpuCount ?? 4) * 100, color: Theme.accent2)
            LabeledBar(label: "RAM", value: memText(m), pct: m.memPct ?? 0, color: Theme.accent2)
        }
    }

    private var chartsPanel: some View {
        Panel(title: "Charts", icon: "chart.xyaxis.line") {
            ChartView(title: "Z (local), m", data: t.chartAlt, color: Theme.dataBlue,
                      minSpan: 1.0, staleNote: poseStatus.note)
            ChartView(title: "Speed (m/s)", data: t.chartSpd, color: Theme.dataTeal, fixedMin: 0, fixedMax: 5,
                      staleNote: velStatus.note)
            ChartView(title: "Battery (%)", data: t.chartBat, color: Theme.dataGreen, fixedMin: 0, fixedMax: 100,
                      staleNote: batStatus.note)
        }
    }

    private var mapPanel: some View {
        let pose = poseStatus
        return Panel(title: "Position Map", icon: "map", note: pose.note, dimmed: !pose.isFresh) {
            PositionMapView(trail: t.posTrail)
        }
    }

    private var logPanel: some View {
        let logs = t.logs
        return Panel(title: "Messages", icon: "list.bullet.rectangle") {
            if logs.count > 16 {
                ScrollView { logList(logs) }.frame(height: 240)
            } else {
                logList(logs)
            }
        }
    }

    private func logList(_ logs: [LogEntry]) -> some View {
        VStack(alignment: .leading, spacing: Theme.s0) {
            if logs.isEmpty { Text("—").font(Theme.monoSmall).foregroundStyle(Theme.muted) }
            ForEach(logs) { e in
                HStack(alignment: .top, spacing: Theme.s1 + 2) {
                    Text(e.time).font(Theme.logMono).foregroundStyle(Theme.muted)
                    Text(e.line).font(Theme.logMono).foregroundStyle(e.source == .fcu ? Theme.caution : Theme.text)
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    /// A group of rows fed by one source: greyed with "no data N s" when quiet.
    private func group<V: View>(_ s: Freshness.Status, @ViewBuilder _ content: () -> V) -> some View {
        VStack(alignment: .leading, spacing: Theme.s3) {
            content().staleDimmed(!s.isFresh)
            StaleNote(status: s)
        }
    }

    // MARK: - Derived

    private func num(_ v: Double?, _ format: String) -> String {
        v.map { String(format: format, $0) } ?? "—"
    }

    private func tempColor(_ x: Double?) -> Color { x.map { $0 < 60 ? Theme.ok : ($0 < 75 ? Theme.warn : Theme.danger) } ?? Theme.muted }
    private func cpuColor(_ x: Double?) -> Color { x.map { $0 < 60 ? Theme.ok : ($0 < 85 ? Theme.warn : Theme.danger) } ?? Theme.muted }
    private func loadText(_ m: SystemMetrics) -> String {
        guard let l1 = m.load1, let l5 = m.load5, let l15 = m.load15 else { return "—" }
        return String(format: "%.2f / %.2f / %.2f", l1, l5, l15)
    }
    private func memText(_ m: SystemMetrics) -> String {
        guard let u = m.memUsed, let tot = m.memTotal, let p = m.memPct else { return "—" }
        return "\(u) / \(tot) MB (\(String(format: "%.0f", p))%)"
    }
}
