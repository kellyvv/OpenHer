import SwiftUI

/// Discovery view — swipeable exhibit carousel with real drag gesture.
/// Uses `appState.displayPersonas` which filters by cabinet image availability
/// when `showOnlyReadyPersonas` is on.
struct DiscoveryView: View {
    @EnvironmentObject var appState: AppState
    @State private var currentIndex: Int = 0

    // Drag gesture state
    @State private var dragOffset: CGFloat = 0
    @GestureState private var isDragging: Bool = false

    /// Convenience: the filtered persona list from AppState
    private var visiblePersonas: [Persona] { appState.displayPersonas }

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Paper.background.ignoresSafeArea()

                if visiblePersonas.isEmpty {
                    loadingState
                } else {
                    showcase(in: geometry.size)
                }
            }
        }
        .ignoresSafeArea()
        .onChange(of: visiblePersonas.count) { _, newCount in
            // Default to Iris on first load
            if newCount > 0, currentIndex == 0 {
                if let irisIndex = visiblePersonas.firstIndex(where: { $0.personaId == "iris" }) {
                    currentIndex = irisIndex
                }
            }
            clampCurrentIndex()
        }
    }

    // MARK: - Navigation Arrow

    private func navArrow(systemName: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 40, weight: .light))
                .foregroundStyle(Color(red: 185/255, green: 155/255, blue: 58/255))
                .frame(width: 50, height: 66)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: - Layout

    @ViewBuilder
    private func showcase(in size: CGSize) -> some View {
        let count = visiblePersonas.count
        let clampedIndex = min(max(currentIndex, 0), count - 1)
        let canvasWidth = size.width
        let canvasHeight = size.height
        let arrowTopSpacing = min(max(canvasHeight * 0.34, 256), 380) + 10

        ZStack(alignment: .top) {
            // === Swipeable card stack ===
            ZStack {
                // Render current card + adjacent cards for peek effect
                ForEach(adjacentIndices(around: clampedIndex, count: count), id: \.self) { index in
                    let offset = CGFloat(index - clampedIndex) * canvasWidth + dragOffset
                    let persona = visiblePersonas[index]

                    PersonaCard(persona: persona) {
                        appState.awakenPersona(persona)
                    }
                    .frame(width: canvasWidth, height: canvasHeight)
                    .offset(x: offset)
                    .zIndex(index == clampedIndex ? 1 : 0)
                }
            }
            .gesture(
                DragGesture(minimumDistance: 20)
                    .updating($isDragging) { _, state, _ in
                        state = true
                    }
                    .onChanged { value in
                        // Elastic resistance at edges
                        let raw = value.translation.width
                        if (clampedIndex == 0 && raw > 0) ||
                           (clampedIndex == count - 1 && raw < 0) {
                            // Rubber-band: 30% of actual drag at edges
                            dragOffset = raw * 0.3
                        } else {
                            dragOffset = raw
                        }
                    }
                    .onEnded { value in
                        let threshold = canvasWidth * 0.2
                        let velocity = value.predictedEndTranslation.width - value.translation.width

                        var newIndex = clampedIndex

                        // Swipe left (next) — drag left or fast flick left
                        if value.translation.width < -threshold || velocity < -200 {
                            newIndex = min(clampedIndex + 1, count - 1)
                        }
                        // Swipe right (prev) — drag right or fast flick right
                        else if value.translation.width > threshold || velocity > 200 {
                            newIndex = max(clampedIndex - 1, 0)
                        }

                        withAnimation(.spring(response: 0.4, dampingFraction: 0.82)) {
                            currentIndex = newIndex
                            dragOffset = 0
                        }
                    }
            )

            // === Navigation arrows ===
            VStack(spacing: 0) {
                Color.clear
                    .frame(height: arrowTopSpacing)

                HStack {
                    navArrow(systemName: "chevron.left") {
                        guard currentIndex > 0 else { return }
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.82)) {
                            currentIndex -= 1
                        }
                    }
                    .opacity(currentIndex > 0 ? 1 : 0.25)
                    .disabled(currentIndex == 0)

                    Spacer(minLength: 0)

                    navArrow(systemName: "chevron.right") {
                        guard currentIndex < count - 1 else { return }
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.82)) {
                            currentIndex += 1
                        }
                    }
                    .opacity(currentIndex < count - 1 ? 1 : 0.25)
                    .disabled(currentIndex >= count - 1)
                }
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 11)

                Spacer(minLength: 0)
            }
            .allowsHitTesting(!isDragging) // Disable arrows during drag
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .clipped() // Clip adjacent cards that slide off-screen
    }

    /// Returns indices for the current card plus its immediate neighbors.
    private func adjacentIndices(around center: Int, count: Int) -> [Int] {
        var result: [Int] = []
        if center - 1 >= 0 { result.append(center - 1) }
        result.append(center)
        if center + 1 < count { result.append(center + 1) }
        return result
    }

    private func clampCurrentIndex() {
        guard !visiblePersonas.isEmpty else {
            currentIndex = 0
            return
        }
        currentIndex = min(max(currentIndex, 0), visiblePersonas.count - 1)
    }

    // MARK: - Loading

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
                .scaleEffect(0.8)
            Text(L10n.str("正在搜索频率...", en: "Scanning frequencies..."))
                .font(Paper.freqFont)
                .foregroundStyle(Paper.faint)
        }
    }
}
