import SwiftUI

/// Discovery persona sheet — fixed exhibit composition tuned for the cabinet reference.
struct PersonaCard: View {
    let persona: Persona
    let onAwaken: () -> Void

    @State private var isAwakening = false

    var body: some View {
        GeometryReader { geometry in
            let size = geometry.size

            ZStack(alignment: .bottom) {
                // === Full-page persona background (cabinet + paper) ===
                cabinetImage(size: size)

                // === BOTTOM: Text overlay — pixel-matched to reference ===
                bottomSection(cardWidth: size.width)
                    .opacity(isAwakening ? 0 : 1)
                    .animation(.easeOut(duration: 0.6), value: isAwakening)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    // MARK: - Cabinet Image with Awakening Transition

    @ViewBuilder
    private func cabinetImage(size: CGSize) -> some View {
        let dormantURL = Bundle.module.url(forResource: persona.id, withExtension: "png", subdirectory: "cabinets")

        if let url = dormantURL, let originalImage = NSImage(contentsOf: url) {
            // Show dormant image only — no crossfade on awaken.
            // AwakeningView will pick up from this same visual state.
            Image(nsImage: originalImage)
                .resizable()
                .aspectRatio(contentMode: .fill)
                .frame(width: size.width, height: size.height)
                .clipped()
        } else {
            PaperBackground()
        }
    }

    // MARK: - Awakening Action

    private func triggerAwakening() {
        guard !isAwakening else { return }

        // Fade out bottom text/button overlay — keep the cabinet image as-is
        withAnimation(.easeOut(duration: 0.6)) {
            isAwakening = true
        }

        // After text fades, transition to AwakeningView
        // Short delay keeps the persona image visible → seamless handoff
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            onAwaken()
        }
    }

    // MARK: - Bottom Section (fixed sizes)

    private func bottomSection(cardWidth: CGFloat) -> some View {
        let buttonWidth = cardWidth - 50  // 25px each side + 12px canvas margin = 37px total

        return VStack(spacing: 0) {
            // Name → 20px below photo
            Spacer().frame(height: 20)

            Text(persona.displayName)
                .font(.system(size: 40, weight: .semibold, design: .serif))
                .foregroundStyle(Color(red: 78/255, green: 58/255, blue: 45/255))
                .lineLimit(1)

            // Subtitle → 6px below name
            Spacer().frame(height: 6)

            Text(subtitleText)
                .font(.custom("Baskerville", size: 20))
                .foregroundStyle(Color(red: 158/255, green: 142/255, blue: 122/255))
                .tracking(0.8)
                .lineLimit(1)

            // Tags → 14px below subtitle
            Spacer().frame(height: 14)

            HStack(spacing: 6) {
                ForEach(persona.tags.prefix(3), id: \.self) { tag in
                    Text("#\(tag)")
                        .font(.custom("Baskerville", size: 14))
                        .foregroundStyle(DiscoveryPalette.buttonText)
                        .padding(.horizontal, 11)
                        .padding(.vertical, 4)
                        .background(
                            Capsule()
                                .fill(Paper.coral)
                        )
                }
            }

            // Button → 24px below tags
            Spacer().frame(height: 24)

            Button(action: triggerAwakening) {
                Text("唤醒")
                    .font(.system(size: 22, weight: .medium, design: .serif))
                    .foregroundStyle(DiscoveryPalette.buttonText)
                    .shadow(color: DiscoveryPalette.buttonTextShadow.opacity(0.28), radius: 0.6, x: 0, y: 1)
                    .frame(maxWidth: .infinity)
                    .frame(height: 50)
                    .background(
                        Capsule()
                            .fill(
                                LinearGradient(
                                    colors: [
                                        DiscoveryPalette.buttonTop,
                                        DiscoveryPalette.buttonBottom,
                                    ],
                                    startPoint: .top,
                                    endPoint: .bottom
                                )
                            )
                    )
                    .shadow(color: DiscoveryPalette.buttonShadow.opacity(0.18), radius: 10, y: 4)
            }
            .buttonStyle(.plain)
            .frame(width: buttonWidth)

            // Bottom margin → 28px (+ ~12px canvas gap = 40px measured)
            Spacer().frame(height: 28)
        }
    }

    // MARK: - Glass Reflection Effect

    @ViewBuilder
    private func glassReflectionOverlay() -> some View {
        ZStack {
            // Diagonal light sweep — simulates overhead light reflecting off glass
            LinearGradient(
                stops: [
                    .init(color: Color.white.opacity(0), location: 0.0),
                    .init(color: Color.white.opacity(0.08), location: 0.25),
                    .init(color: Color.white.opacity(0.15), location: 0.35),
                    .init(color: Color.white.opacity(0.04), location: 0.5),
                    .init(color: Color.white.opacity(0), location: 0.7),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .allowsHitTesting(false)

            // Subtle vertical edge highlight — left glass panel reflection
            HStack(spacing: 0) {
                LinearGradient(
                    colors: [
                        Color.white.opacity(0.12),
                        Color.white.opacity(0),
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .frame(width: 30)

                Spacer()

                // Right edge — fainter reflection
                LinearGradient(
                    colors: [
                        Color.white.opacity(0),
                        Color.white.opacity(0.06),
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .frame(width: 20)
            }
            .allowsHitTesting(false)

            // Top edge light — overhead light hitting the glass top
            VStack(spacing: 0) {
                LinearGradient(
                    colors: [
                        Color.white.opacity(0.1),
                        Color.white.opacity(0),
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 40)

                Spacer()
            }
            .allowsHitTesting(false)
        }
    }

    // MARK: - Cabinet Artwork

    @ViewBuilder
    private var glassCabinet: some View {
        if let nsImage = loadCabinetImage() {
            let contentMode: ContentMode = nsImage.size.height > nsImage.size.width * 1.15 ? .fit : .fill

            Image(nsImage: nsImage)
                .resizable()
                .interpolation(.high)
                .antialiased(true)
                .aspectRatio(contentMode: contentMode)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .clipped()
                .shadow(color: Paper.herText.opacity(0.14), radius: 28, y: 16)
        } else {
            fallbackCabinet
        }
    }

    private var fallbackCabinet: some View {
        ZStack(alignment: .bottom) {
            Rectangle()
                .fill(Color(red: 236 / 255, green: 224 / 255, blue: 206 / 255))

            ZStack(alignment: .bottom) {
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .stroke(
                        LinearGradient(
                            colors: [
                                Color(red: 148 / 255, green: 109 / 255, blue: 58 / 255),
                                Color(red: 208 / 255, green: 174 / 255, blue: 107 / 255),
                                Color(red: 130 / 255, green: 88 / 255, blue: 42 / 255),
                            ],
                            startPoint: .leading,
                            endPoint: .trailing
                        ),
                        lineWidth: 6
                    )
                    .padding(.horizontal, 42)
                    .padding(.top, 28)
                    .padding(.bottom, 48)

                RoundedRectangle(cornerRadius: 3, style: .continuous)
                    .fill(Color.white.opacity(0.18))
                    .padding(.horizontal, 50)
                    .padding(.top, 36)
                    .padding(.bottom, 56)
                    .overlay(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.28),
                                Color.clear,
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                        .padding(.horizontal, 50)
                        .padding(.top, 36)
                        .padding(.bottom, 56)
                    )

                Text(String(persona.displayName.prefix(1)))
                    .font(.system(size: 150, weight: .thin, design: .serif))
                    .foregroundStyle(Paper.faint.opacity(0.35))
                    .padding(.bottom, 130)

                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(Color(red: 94 / 255, green: 60 / 255, blue: 41 / 255))
                    .frame(width: 70, height: 104)
                    .padding(.bottom, 82)

                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 80 / 255, green: 50 / 255, blue: 34 / 255),
                                Color(red: 126 / 255, green: 83 / 255, blue: 56 / 255),
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .frame(height: 24)
                    .padding(.horizontal, 26)
            }
        }
        .shadow(color: Paper.herText.opacity(0.1), radius: 24, y: 16)
    }

    /// Load the cabinet PNG for this persona from the bundle.
    /// Looks for `cabinets/{personaId}.png` inside Bundle.module.
    private func loadCabinetImage() -> NSImage? {
        let url = Bundle.module.url(
            forResource: persona.personaId,
            withExtension: "png",
            subdirectory: "cabinets"
        )
        guard let url = url else { return nil }
        return NSImage(contentsOf: url)
    }

    // MARK: - Helpers

    private var subtitleText: String {
        var parts: [String] = []
        if let mbti = persona.mbti { parts.append(mbti) }
        if let age = persona.age { parts.append("\(age)") }
        if let desc = persona.description, !desc.isEmpty {
            // Strip redundant age prefix (e.g. "20岁，") since age shown separately
            var clean = desc
            if let age = persona.age {
                for prefix in ["\(age)岁，", "\(age)岁,"] {
                    if clean.hasPrefix(prefix) {
                        clean = String(clean.dropFirst(prefix.count))
                        break
                    }
                }
            }
            // Take only the first phrase (occupation)
            let first = clean.components(separatedBy: "，").first ?? clean
            parts.append(first)
        }
        return parts.joined(separator: " · ")
    }
}

private enum DiscoveryPalette {
    static let coral = Color(red: 231 / 255, green: 97 / 255, blue: 74 / 255)
    static let coralLight = Color(red: 238 / 255, green: 118 / 255, blue: 94 / 255)
    static let buttonTop = Color(red: 236 / 255, green: 106 / 255, blue: 84 / 255)
    static let buttonBottom = Color(red: 232 / 255, green: 98 / 255, blue: 74 / 255)
    static let buttonText = Color(red: 238 / 255, green: 224 / 255, blue: 200 / 255)
    static let buttonTextShadow = Color(red: 158 / 255, green: 89 / 255, blue: 75 / 255)
    static let buttonShadow = Color(red: 166 / 255, green: 80 / 255, blue: 62 / 255)
}
