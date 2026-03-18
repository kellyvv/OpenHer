import SwiftUI

/// Developer mode panel — right sidebar showing real-time Genome Engine state.
/// Visual style: 暖羊皮纸 + 黄铜蚀刻 + 冷蓝激活, matching persona_engine_viz.html.
struct EngineDebugPanel: View {
    @ObservedObject var debugState: EngineDebugState

    // Signal order matches backend SIGNALS list (not alphabetical)
    private let signalOrder = ["directness", "vulnerability", "playfulness", "initiative",
                               "depth", "warmth", "defiance", "curiosity"]
    private let signalColors: [Color] = [
        Color(red: 0.42, green: 0.62, blue: 0.75),
        Color(red: 0.61, green: 0.50, blue: 0.80),
        Color(red: 0.80, green: 0.42, blue: 0.53),
        Color(red: 0.35, green: 0.62, blue: 0.47),
        Color(red: 0.35, green: 0.67, blue: 0.75),
        Color(red: 0.78, green: 0.53, blue: 0.29),
        Color(red: 0.75, green: 0.34, blue: 0.34),
        Color(red: 0.78, green: 0.63, blue: 0.19),
    ]
    private let driveNames  = ["connection", "novelty", "expression", "safety", "play"]
    private let driveIcons  = ["🔗", "✨", "💬", "🛡️", "🎭"]

    // Color tokens matching CSS variables
    private let bgSidebar = Color(red: 0.90, green: 0.85, blue: 0.75)   // --bg-sidebar: #e6d8c0
    private let brass     = Color(red: 0.72, green: 0.55, blue: 0.20)   // --gold: #b8892a
    private let ink       = Color(red: 0.24, green: 0.14, blue: 0.09)   // --text-1: #2e1a0e
    private let ink2      = Color(red: 0.24, green: 0.14, blue: 0.09).opacity(0.58)
    private let ink3      = Color(red: 0.24, green: 0.14, blue: 0.09).opacity(0.36)
    private let barBg     = Color(red: 0.72, green: 0.55, blue: 0.20).opacity(0.10)

    var body: some View {
        VStack(spacing: 0) {
            // ── Header ──
            header

            // Left border accent (inset shadow substitute)
            Rectangle()
                .fill(brass.opacity(0.18))
                .frame(height: 1)

            ScrollView(.vertical, showsIndicators: false) {
                VStack(spacing: 0) {
                    // ── Neural Network Canvas ──
                    NeuralNetworkView(debugState: debugState)
                        .frame(height: 360)

                    Rectangle()
                        .fill(brass.opacity(0.18))
                        .frame(height: 1)
                        .padding(.vertical, 14)

                    VStack(alignment: .leading, spacing: 16) {
                        signalBarsSection
                        driveBarsSection
                        metabolismSection
                        monologueSection
                        recallSection
                    }
                    .padding(.horizontal, 18)
                    .padding(.bottom, 22)
                }
            }
        }
        .background(bgSidebar)
        .overlay(alignment: .leading) {
            // Left edge border
            Rectangle()
                .fill(brass.opacity(0.18))
                .frame(width: 1)
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 7) {
            // Status pulse dot
            TimelineView(.periodic(from: .now, by: 0.05)) { tl in
                let t = tl.date.timeIntervalSince1970
                let pulse = 0.55 + sin(t * 2.618) * 0.35
                Circle()
                    .fill(brass)
                    .shadow(color: brass.opacity(0.55), radius: 3)
                    .frame(width: 5, height: 5)
                    .opacity(pulse)
            }

            Text("PERSONA ENGINE")
                .font(.system(size: 9, weight: .regular, design: .monospaced))
                .foregroundColor(brass.opacity(0.65))
                .tracking(3)

            Spacer()

            Text(debugState.isComputing ? "COMPUTING" : "IDLE")
                .font(.system(size: 9, weight: .regular, design: .monospaced))
                .foregroundColor(ink3)
                .tracking(0.5)

            Text("t=\(debugState.turnCount)")
                .font(.system(size: 9, weight: .regular, design: .monospaced))
                .foregroundColor(ink3)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
    }

    // MARK: - Section Title

    private func sectionTitle(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(text)
                .font(.system(size: 9, weight: .regular, design: .monospaced))
                .foregroundColor(brass.opacity(0.75))
                .tracking(2.5)
            Rectangle()
                .fill(brass.opacity(0.30))
                .frame(height: 1)
        }
        .padding(.bottom, 4)
    }

    // MARK: - Signal Bars

    private var signalBarsSection: some View {
        VStack(alignment: .leading, spacing: 7) {
            sectionTitle("BEHAVIORAL SIGNALS")
            ForEach(Array(signalOrder.enumerated()), id: \.element) { i, name in
                let val = debugState.signals[name] ?? 0.5
                let color = i < signalColors.count ? signalColors[i] : .gray
                signalBarRow(name: name, value: val, color: color)
            }
        }
    }

    private func signalBarRow(name: String, value: Double, color: Color) -> some View {
        HStack(spacing: 9) {
            Text(name)
                .font(.system(size: 11))
                .foregroundColor(ink2)
                .frame(width: 82, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(barBg)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(LinearGradient(
                            colors: [color.opacity(0.55), color.opacity(0.9)],
                            startPoint: .leading, endPoint: .trailing
                        ))
                        .shadow(color: color.opacity(0.30), radius: 3, x: 0, y: 0)
                        .frame(width: geo.size.width * CGFloat(min(1, max(0, value))))
                        .animation(.interpolatingSpring(stiffness: 80, damping: 18), value: value)
                }
            }
            .frame(height: 7)

            Text(String(format: "%.2f", value))
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(ink2)
                .frame(width: 32, alignment: .trailing)
        }
    }

    // MARK: - Drive Bars

    private var driveBarsSection: some View {
        VStack(alignment: .leading, spacing: 9) {
            sectionTitle("INNER DRIVES")
            ForEach(0..<driveNames.count, id: \.self) { i in
                let name = driveNames[i]
                let val      = debugState.driveState[name]    ?? 0.5
                let baseline = debugState.driveBaseline[name] ?? 0.5
                driveBarRow(icon: driveIcons[i], name: name, value: val, baseline: baseline)
            }
        }
    }

    private func driveBarRow(icon: String, name: String, value: Double, baseline: Double) -> some View {
        HStack(spacing: 8) {
            Text(icon)
                .font(.system(size: 13))
                .frame(width: 18)

            Text(name)
                .font(.system(size: 11))
                .foregroundColor(ink2)
                .frame(width: 68, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(barBg)

                    RoundedRectangle(cornerRadius: 3)
                        .fill(LinearGradient(
                            colors: [
                                Color(red: 0.78, green: 0.53, blue: 0.24).opacity(0.65),
                                Color(red: 0.78, green: 0.44, blue: 0.27).opacity(0.92),
                            ],
                            startPoint: .leading, endPoint: .trailing
                        ))
                        .shadow(color: Color(red: 0.78, green: 0.44, blue: 0.27).opacity(0.22), radius: 3)
                        .frame(width: geo.size.width * CGFloat(min(1, max(0, value))))
                        .animation(.interpolatingSpring(stiffness: 80, damping: 18), value: value)

                    // Baseline marker
                    Rectangle()
                        .fill(ink.opacity(0.28))
                        .frame(width: 1, height: geo.size.height + 4)
                        .offset(x: geo.size.width * CGFloat(baseline) - 0.5, y: -2)
                }
            }
            .frame(height: 5)

            Text(String(format: "%.2f", value))
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(ink3)
                .frame(width: 28, alignment: .trailing)
        }
    }

    // MARK: - Metabolism (Frustration + Temperature)

    private var metabolismSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionTitle("FRUSTRATION · σ NOISE")

            // Frustration bar — gradient gold→coral→red
            VStack(spacing: 5) {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 3).fill(barBg)
                        RoundedRectangle(cornerRadius: 3)
                            .fill(LinearGradient(
                                colors: [
                                    Color(red: 0.78, green: 0.63, blue: 0.19),
                                    Color(red: 0.78, green: 0.44, blue: 0.35),
                                    Color(red: 0.72, green: 0.25, blue: 0.25),
                                ],
                                startPoint: .leading, endPoint: .trailing
                            ))
                            .frame(width: geo.size.width * CGFloat(min(1, debugState.frustration / 2.0)))
                            .animation(.easeOut(duration: 0.5), value: debugState.frustration)
                    }
                }
                .frame(height: 5)

                HStack {
                    Text("0.0")
                    Spacer()
                    Text(String(format: "%.2f", debugState.frustration))
                    Spacer()
                    Text("⚡ 2.0")
                }
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(ink3)
            }

            // Temperature bar — cool blue→purple→red
            HStack(spacing: 8) {
                Text("σ")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(ink3)
                    .frame(width: 14)

                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 3).fill(barBg)
                        RoundedRectangle(cornerRadius: 3)
                            .fill(LinearGradient(
                                colors: [
                                    Color(red: 0.38, green: 0.65, blue: 0.98),
                                    Color(red: 0.65, green: 0.55, blue: 0.98),
                                    Color(red: 0.93, green: 0.27, blue: 0.27),
                                ],
                                startPoint: .leading, endPoint: .trailing
                            ))
                            .frame(width: geo.size.width * CGFloat(min(1, debugState.temperature / 0.35)))
                            .animation(.easeOut(duration: 0.5), value: debugState.temperature)
                    }
                }
                .frame(height: 4)

                Text(String(format: "%.3f", debugState.temperature))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(ink3)
                    .frame(width: 40, alignment: .trailing)
            }
        }
    }

    // MARK: - Monologue

    private var monologueSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            sectionTitle("FEEL · 内心独白")

            Text(debugState.monologue.isEmpty ? "等待计算..." : debugState.monologue)
                .font(.system(size: 13, weight: .regular, design: .serif))
                .italic()
                .foregroundColor(ink.opacity(0.70))
                .lineSpacing(5)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color(red: 0.78, green: 0.44, blue: 0.35).opacity(0.06))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .strokeBorder(Color(red: 0.78, green: 0.44, blue: 0.35).opacity(0.18))
                        )
                )
        }
    }

    // MARK: - Style Memory Recall

    private var recallSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            sectionTitle("STYLE MEMORY RECALL")

            if debugState.styleRecall.isEmpty {
                Text("—")
                    .font(.system(size: 10))
                    .foregroundColor(ink3)
            } else {
                ForEach(debugState.styleRecall) { item in
                    HStack(alignment: .firstTextBaseline) {
                        Text("\"\(item.text)\"")
                            .font(.system(size: 11))
                            .foregroundColor(ink2)
                            .lineLimit(1)
                        Spacer()
                        Text("d=\(String(format: "%.2f", item.distance))")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(ink3)
                    }
                    .padding(.vertical, 7)
                    .overlay(alignment: .bottom) {
                        Rectangle().fill(brass.opacity(0.14)).frame(height: 1)
                    }
                }
            }
        }
    }
}
