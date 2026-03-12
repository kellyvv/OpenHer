import SwiftUI
import AppKit

/// Minimal header — persona name with typing indicator.
/// Also serves as the window drag region since we use hiddenTitleBar.
struct AvatarHeader: View {
    let persona: Persona?
    let isConnected: Bool
    let isTyping: Bool
    let avatarURL: URL?

    var body: some View {
        VStack(spacing: 2) {
            Text(persona?.displayName ?? "")
                .font(Paper.nameFont)
                .foregroundStyle(Paper.herText)

            // Typing / connection status
            if isTyping {
                HStack(spacing: 4) {
                    ForEach(0..<3, id: \.self) { i in
                        Circle()
                            .fill(Paper.coral)
                            .frame(width: 4, height: 4)
                            .opacity(0.7)
                    }
                    Text(L10n.str("正在输入", en: "typing"))
                        .font(.system(size: 11, weight: .regular))
                        .foregroundStyle(Paper.faint)
                }
                .transition(.opacity)
            } else {
                HStack(spacing: 4) {
                    Circle()
                        .fill(isConnected ? Color.green.opacity(0.7) : Paper.faint.opacity(0.4))
                        .frame(width: 5, height: 5)
                    Text(isConnected ? L10n.str("在线", en: "online") : L10n.str("离线", en: "offline"))
                        .font(.system(size: 11, weight: .regular))
                        .foregroundStyle(Paper.faint)
                }
                .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: isTyping)
        .frame(maxWidth: .infinity)
        .padding(.top, 16)
        .padding(.bottom, 8)
        .background(WindowDragArea())
    }
}

// MARK: - Window Drag Support

/// Invisible NSView overlay that forwards mouseDown to window.performDrag,
/// enabling window dragging from the header area.
private struct WindowDragArea: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        DraggableView()
    }
    func updateNSView(_ nsView: NSView, context: Context) {}
}

private class DraggableView: NSView {
    override func mouseDown(with event: NSEvent) {
        window?.performDrag(with: event)
    }
}
