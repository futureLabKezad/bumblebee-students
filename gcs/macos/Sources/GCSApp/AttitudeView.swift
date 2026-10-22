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

/// Artificial horizon (attitude indicator). Roll rotates the horizon, pitch
/// shifts it vertically; includes a pitch ladder, roll arc and fixed aircraft
/// marker — same construction as the web canvas.
///
/// Pitch is in the ROS convention (+ = nose down, like get_telemetry()): nose
/// down moves the horizon up, so more ground shows (Horizon.offset).
/// Before the first attitude arrives (nil) no horizon is drawn: a level
/// horizon would claim 0° that nobody measured.
struct AttitudeView: View {
    let roll: Double?   // degrees
    let pitch: Double?  // degrees, + = nose down

    private let sky = Color(hex: 0x1a4cc0)
    private let ground = Color(hex: 0x7c4820)

    var body: some View {
        Canvas { ctx, size in
            let cx = size.width / 2, cy = size.height / 2
            let r = min(cx, cy) - 2
            let pxPerDeg = cy / 45.0
            let circle = Path(ellipseIn: CGRect(x: cx - r, y: cy - r, width: 2 * r, height: 2 * r))

            guard let roll = roll, let pitch = pitch else {
                ctx.fill(circle, with: .color(Theme.surfaceRaised))
                ctx.stroke(circle, with: .color(Theme.border), lineWidth: 2)
                return
            }

            // Horizon layer (clipped, rolled, pitched).
            var h = ctx
            h.clip(to: circle)
            h.translateBy(x: cx, y: cy)
            h.rotate(by: .degrees(-roll))
            h.translateBy(x: 0, y: Horizon.offset(pitchDeg: pitch, pxPerDeg: pxPerDeg))

            let big = max(size.width, size.height) * 2
            h.fill(Path(CGRect(x: -big, y: -big, width: 2 * big, height: big)), with: .color(sky))
            h.fill(Path(CGRect(x: -big, y: 0, width: 2 * big, height: big)), with: .color(ground))
            h.stroke(Path { p in p.move(to: CGPoint(x: -big, y: 0)); p.addLine(to: CGPoint(x: big, y: 0)) },
                     with: .color(.white), lineWidth: 1.5)

            for deg in stride(from: -30, through: 30, by: 10) where deg != 0 {
                let y = -Double(deg) * pxPerDeg
                let w: CGFloat = deg % 30 == 0 ? 30 : 20
                h.stroke(Path { p in p.move(to: CGPoint(x: -w, y: y)); p.addLine(to: CGPoint(x: w, y: y)) },
                         with: .color(.white.opacity(0.8)), lineWidth: 1)
                let txt = Text("\(abs(deg))").font(Theme.micro).foregroundColor(.white)
                h.draw(txt, at: CGPoint(x: w + 10, y: y))
            }

            // Roll arc layer (clipped, only rolled).
            var a = ctx
            a.clip(to: circle)
            a.translateBy(x: cx, y: cy)
            a.rotate(by: .degrees(-roll))
            for deg in [-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60] {
                let ang = Double(deg) * .pi / 180 - .pi / 2
                let r1 = r - 2, r2 = r - (deg % 30 == 0 ? 10 : 6)
                let p1 = CGPoint(x: cos(ang) * r1, y: sin(ang) * r1)
                let p2 = CGPoint(x: cos(ang) * r2, y: sin(ang) * r2)
                a.stroke(Path { p in p.move(to: p1); p.addLine(to: p2) },
                         with: .color(.white.opacity(0.7)), lineWidth: 1)
            }

            // Fixed aircraft marker + bezel.
            ctx.stroke(circle, with: .color(Theme.border), lineWidth: 2)
            let mark = Path { p in
                p.move(to: CGPoint(x: cx - 30, y: cy)); p.addLine(to: CGPoint(x: cx - 10, y: cy))
                p.move(to: CGPoint(x: cx + 10, y: cy)); p.addLine(to: CGPoint(x: cx + 30, y: cy))
                p.addEllipse(in: CGRect(x: cx - 2, y: cy - 2, width: 4, height: 4))
            }
            ctx.stroke(mark, with: .color(Theme.caution), lineWidth: 2)
            // Top roll pointer (fixed triangle).
            let tri = Path { p in
                p.move(to: CGPoint(x: cx, y: cy - r + 2))
                p.addLine(to: CGPoint(x: cx - 6, y: cy - r + 12))
                p.addLine(to: CGPoint(x: cx + 6, y: cy - r + 12))
                p.closeSubpath()
            }
            ctx.fill(tri, with: .color(Theme.caution))
        }
        .frame(width: 186, height: 186)
    }
}
