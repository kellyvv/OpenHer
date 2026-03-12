import SwiftUI

/// The main conversation panel — single persona, paper aesthetic.
/// Layout: AvatarHeader → ScrollView(messages) with FrequencyIndicator on left → InputLine
struct ConversationPanel: View {
    @EnvironmentObject var appState: AppState
    @State private var inputText = ""
    @FocusState private var inputFocused: Bool
    @State private var showScrollButton = false
    @State private var scrollProxy: ScrollViewProxy?

    var body: some View {
        ZStack {
            // Chat background image
            GeometryReader { geo in
                if let url = Bundle.module.url(forResource: "chat_bg", withExtension: "png"),
                   let nsImage = NSImage(contentsOf: url) {
                    Image(nsImage: nsImage)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: geo.size.width, height: geo.size.height)
                        .clipped()
                } else {
                    Paper.background
                }
            }
            .ignoresSafeArea()

            if appState.selectedPersona != nil {
                conversationContent
            } else {
                emptyState
            }
        }
    }

    // MARK: - Conversation Content

    private var conversationContent: some View {
        VStack(spacing: 0) {
            // Minimal header
            AvatarHeader(
                persona: appState.selectedPersona,
                isConnected: appState.isConnected,
                isTyping: appState.isTyping,
                avatarURL: avatarURL
            )

            // Messages area with frequency indicator on left
            ZStack(alignment: .bottomTrailing) {
                HStack(alignment: .top, spacing: 0) {
                    // Left frequency indicator
                    FrequencyIndicator(
                        valence: appState.valence,
                        lastReward: appState.lastReward,
                        temperature: appState.emotionTemperature,
                        crystalCount: appState.crystalCount
                    )

                    // Messages scroll
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: Paper.messageSpacing) {
                                ForEach(appState.messages) { message in
                                    MessageRow(
                                        message: message,
                                        onRetry: message.sendStatus == .failed ? {
                                            appState.retryMessage(id: message.id)
                                        } : nil
                                    )
                                    .id(message.id)
                                }

                                // Typing indicator
                                if appState.isTyping {
                                    typingIndicator
                                }
                            }
                            .padding(.leading, 12)
                            .padding(.trailing, Paper.hPadding)
                            .padding(.vertical, 16)

                            // Invisible anchor at the very bottom for scroll detection
                            Color.clear
                                .frame(height: 1)
                                .id("bottom")
                                .onAppear { showScrollButton = false }
                                .onDisappear { showScrollButton = true }
                        }
                        .scrollContentBackground(.hidden)
                        .onAppear { scrollProxy = proxy }
                        .onChange(of: appState.messages.count) { _, _ in
                            scrollToBottom(proxy: proxy)
                        }
                        .onChange(of: appState.isTyping) { _, _ in
                            scrollToBottom(proxy: proxy)
                        }
                    }
                }

                // Scroll to bottom button — appears when scrolled up
                if showScrollButton {
                    Button {
                        if let proxy = scrollProxy {
                            withAnimation(.easeOut(duration: 0.3)) {
                                proxy.scrollTo("bottom", anchor: .bottom)
                            }
                        }
                    } label: {
                        Image(systemName: "chevron.down")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(Paper.herText)
                            .frame(width: 28, height: 28)
                            .background(
                                Circle()
                                    .fill(Paper.background)
                                    .shadow(color: Paper.faint.opacity(0.3), radius: 4, y: 2)
                            )
                    }
                    .buttonStyle(.plain)
                    .padding(.trailing, 16)
                    .padding(.bottom, 8)
                    .transition(.opacity.combined(with: .scale(scale: 0.8)))
                }
            }

            // Input line at bottom
            InputLine(
                text: $inputText,
                isFocused: $inputFocused,
                onSend: sendMessage
            )
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Text("✧✦✧")
                .font(.system(size: 32))
                .foregroundStyle(Paper.faint)
            Text(L10n.str("等待调频", en: "Tuning..."))
                .font(Paper.freqFont)
                .foregroundStyle(Paper.faint)
        }
    }

    // MARK: - Typing Indicator

    private var typingIndicator: some View {
        HStack(spacing: 0) {
            HStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { i in
                    Circle()
                        .fill(Paper.coral)
                        .frame(width: 5, height: 5)
                        .opacity(0.6)
                }
            }
            .padding(.vertical, 8)

            Spacer()
        }
        .id("typing")
    }

    // MARK: - Helpers

    private var avatarURL: URL? {
        guard let persona = appState.selectedPersona else { return nil }
        return appState.apiClient.avatarURL(for: persona.personaId)
    }

    private func sendMessage() {
        let trimmed = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        inputText = ""
        appState.sendMessage(trimmed)
    }

    private func scrollToBottom(proxy: ScrollViewProxy) {
        withAnimation(.easeOut(duration: 0.3)) {
            if appState.isTyping {
                proxy.scrollTo("typing", anchor: .bottom)
            } else if let last = appState.messages.last {
                proxy.scrollTo(last.id, anchor: .bottom)
            }
        }
    }
}
