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
        VStack(spacing: 6) {
            // Avatar — real face photo, placed on paper
            if let url = avatarURL {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .overlay(
                                Color(red: 0.82, green: 0.70, blue: 0.55)
                                    .opacity(0.15)
                                    .blendMode(.multiply)
                            )
                    default:
                        Image(systemName: "person.fill")
                            .foregroundStyle(Paper.faint)
                    }
                }
                .frame(width: 50, height: 66)
                .mask(
                    RadialGradient(
                        gradient: Gradient(colors: [
                            .black,
                            .black.opacity(0.95),
                            .black.opacity(0.6),
                            .clear
                        ]),
                        center: .center,
                        startRadius: 15,
                        endRadius: 38
                    )
                )
                .rotationEffect(.degrees(-1.5))
            }

            Text(persona?.displayName ?? "")
                .font(.system(size: 16, weight: .regular))
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
