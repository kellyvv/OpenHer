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
        }
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
