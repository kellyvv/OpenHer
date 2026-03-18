import SwiftUI

/// Root view — layered with iOS-style spring slide-up for awakening exit.
struct RootView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        ZStack {
            Paper.background.ignoresSafeArea()

            // Loading — show nothing, just background
            // (prevents Discovery from flashing before restore completes)

            // Conversation sits BEHIND — revealed when awakening slides up
            if appState.appPhase == .conversation {
                ConversationPanel()
                    .zIndex(1)
            }

            // Discovery
            if appState.appPhase == .discovery {
                DiscoveryView()
                    .zIndex(2)
            }

            // Awakening — slides up with spring (like iOS Control Center dismiss)
            if case .awakening(let persona) = appState.appPhase {
                AwakeningView(persona: persona)
                    .zIndex(3)
                    .transition(
                        .asymmetric(
                            insertion: .identity,
                            removal: .move(edge: .top).combined(with: .opacity)
                        )
                    )
            }
        }
        // Spring animation — silky with slight deceleration, no bounce
        .animation(.spring(response: 0.55, dampingFraction: 0.88, blendDuration: 0), value: appState.appPhase)
    }
}
