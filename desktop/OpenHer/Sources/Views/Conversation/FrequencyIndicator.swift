import SwiftUI

/// Minimal left-margin frequency indicator: a hairline vertical stroke with a coral dot.
///
/// Position = blend of per-turn reward, temperature, and EMA valence.
/// The dot moves dynamically each turn, not just accumulating upward.
/// On crystallization, a radiant pulse ring expands from the dot.
struct FrequencyIndicator: View {
    let valence: Double          // EMA valence (-1…1), slow-moving anchor
    let lastReward: Double       // per-turn reward (-1…1), fluctuates each turn
    let temperature: Double      // metabolism temperature (0…1), per-turn
    let crystalCount: Int        // increases when a new memory crystallizes

    // Crystal pulse animation
    @State private var crystalRingScale: CGFloat = 1.0
    @State private var crystalOpacity: Double = 0.0

    // Breathing animation
    @State private var breathPhase: Bool = false

    /// Blended dot ratio: 0.0 = bottom, 1.0 = top
    /// Combines per-turn reward (immediate response) with valence (stability)
    /// and temperature (energy level).
    private var dotRatio: CGFloat {
        // Blend: 50% per-turn reward + 30% EMA valence + 20% temperature
        let blended = lastReward * 0.5 + valence * 0.3 + (temperature - 0.5) * 0.4
        // Map -1…1 → 0.1…0.9
        let clamped = max(-1.0, min(1.0, blended))
        let ratio = 0.5 + CGFloat(clamped) * 0.4
        return max(0.08, min(0.92, ratio))
    }

    /// Dot color shifts based on reward direction
    private var dotColor: Color {
        if lastReward > 0.05 {
            return Paper.coral       // positive turn → warm coral
        } else if lastReward < -0.05 {
            return Color(red: 0.55, green: 0.50, blue: 0.45)  // negative → muted
        } else {
            return Paper.coral.opacity(0.7)  // neutral
        }
    }

    var body: some View {
        GeometryReader { geo in
            let height = geo.size.height
            let dotY = height * (1.0 - dotRatio)
            let centerY = height * 0.5
            let lineX: CGFloat = 12

            // Hairline vertical stroke
            Path { path in
                path.move(to: CGPoint(x: lineX, y: 0))
                path.addLine(to: CGPoint(x: lineX, y: height))
            }
            .stroke(Paper.faint.opacity(0.35), lineWidth: 0.5)

            // Glow trail from center to dot position
            Path { path in
                path.move(to: CGPoint(x: lineX, y: centerY))
                path.addLine(to: CGPoint(x: lineX, y: dotY))
            }
            .stroke(
                dotColor.opacity(0.3),
                style: StrokeStyle(lineWidth: 2.5, lineCap: .round)
            )
            .animation(.easeInOut(duration: 1.2), value: dotRatio)

            // Crystal pulse ring
            Circle()
                .stroke(Paper.coral.opacity(crystalOpacity * 0.8), lineWidth: 1.5)
                .frame(width: 20, height: 20)
                .scaleEffect(crystalRingScale)
                .position(x: lineX, y: dotY)

            // Inner crystal glow
            Circle()
                .fill(Paper.coral.opacity(crystalOpacity * 0.4))
                .frame(width: 12, height: 12)
                .scaleEffect(crystalRingScale * 0.7)
                .position(x: lineX, y: dotY)

            // Coral dot — breathing gently
            Circle()
                .fill(dotColor)
                .frame(width: 6, height: 6)
                .scaleEffect(breathPhase ? 1.15 : 1.0)
                .shadow(color: dotColor.opacity(0.5), radius: breathPhase ? 6 : 2)
                .position(x: lineX, y: dotY)
                .animation(.interpolatingSpring(stiffness: 25, damping: 7), value: dotRatio)
        }
        .frame(width: 24)
        .onAppear {
            withAnimation(.easeInOut(duration: 2.5).repeatForever(autoreverses: true)) {
                breathPhase = true
            }
        }
        .onChange(of: crystalCount) { oldVal, newVal in
            guard newVal > oldVal else { return }
            triggerCrystalPulse()
        }
    }

    private func triggerCrystalPulse() {
        crystalRingScale = 1.0
        crystalOpacity = 1.0
        withAnimation(.easeOut(duration: 1.5)) {
            crystalRingScale = 3.5
            crystalOpacity = 0.0
        }
    }
}
