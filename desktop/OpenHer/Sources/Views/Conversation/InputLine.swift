import SwiftUI

/// Minimal input line — text field + coral 🎤 + blue ➤.
struct InputLine: View {
    @Binding var text: String
    @FocusState.Binding var isFocused: Bool
    var onSend: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            // Text input (no border, no box)
            TextField("说点什么...", text: $text, axis: .vertical)
                .textFieldStyle(.plain)
                .font(Paper.inputFont)
                .foregroundStyle(Paper.herText)
                .lineLimit(1...4)
                .focused($isFocused)
                .onSubmit {
                    if !NSEvent.modifierFlags.contains(.shift) {
                        onSend()
                    }
                }

            // Coral microphone
            Button(action: {}) {
                Image(systemName: "mic")
                    .font(.system(size: 16))
                    .foregroundStyle(Paper.coral)
            }
            .buttonStyle(.plain)

            // Blue send arrow
            Button(action: onSend) {
                Image(systemName: "arrowtriangle.right.fill")
                    .font(.system(size: 16))
                    .foregroundStyle(
                        text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        ? Paper.faint
                        : Paper.ink
                    )
            }
            .buttonStyle(.plain)
            .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(.horizontal, Paper.hPadding)
        .padding(.top, 14)
        .padding(.bottom, 16)
    }
}
