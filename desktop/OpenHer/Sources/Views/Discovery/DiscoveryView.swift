import SwiftUI

/// Discovery view — fixed exhibit layout instead of a generic adaptive carousel.
struct DiscoveryView: View {
    @EnvironmentObject var appState: AppState
    @State private var currentIndex: Int = 0

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                Paper.background.ignoresSafeArea()

                if appState.personas.isEmpty {
                    loadingState
                } else {
                    showcase(in: geometry.size)
                }
            }
        }
        .ignoresSafeArea()
        .onChange(of: appState.personas.count) { _, newCount in
            // Default to Iris on first load
            if newCount > 0, currentIndex == 0 {
                if let irisIndex = appState.personas.firstIndex(where: { $0.personaId == "iris" }) {
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
        let clampedIndex = min(max(currentIndex, 0), appState.personas.count - 1)
        let persona = appState.personas[clampedIndex]
        let canvasWidth = size.width
        let canvasHeight = size.height
        let arrowRailWidth = min(canvasWidth + 196, size.width - 20)
        let arrowTopSpacing = min(max(canvasHeight * 0.34, 256), 380) + 10

        ZStack(alignment: .top) {
            PersonaCard(persona: persona) {
                appState.awakenPersona(persona)
            }
            .id(persona.id)
            .frame(width: canvasWidth, height: canvasHeight)
            .transition(.opacity.combined(with: .scale(scale: 0.985)))

            VStack(spacing: 0) {
                Color.clear
                    .frame(height: arrowTopSpacing)

                HStack {
                    navArrow(systemName: "chevron.left") {
                        guard currentIndex > 0 else { return }
                        withAnimation(.easeInOut(duration: 0.28)) {
                            currentIndex -= 1
                        }
                    }
                    .opacity(currentIndex > 0 ? 1 : 1)
                    .disabled(currentIndex == 0)

                    Spacer(minLength: 0)

                    navArrow(systemName: "chevron.right") {
                        guard currentIndex < appState.personas.count - 1 else { return }
                        withAnimation(.easeInOut(duration: 0.28)) {
                            currentIndex += 1
                        }
                    }
                    .opacity(currentIndex < appState.personas.count - 1 ? 1 : 1)
                    .disabled(currentIndex >= appState.personas.count - 1)
                }
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 11)

                Spacer(minLength: 0)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)

        .animation(.easeInOut(duration: 0.28), value: currentIndex)
    }

    private func clampCurrentIndex() {
        guard !appState.personas.isEmpty else {
            currentIndex = 0
            return
        }
        currentIndex = min(max(currentIndex, 0), appState.personas.count - 1)
    }

    // MARK: - Loading

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
                .scaleEffect(0.8)
            Text("正在搜索频率...")
                .font(Paper.freqFont)
                .foregroundStyle(Paper.faint)
        }
    }
}
