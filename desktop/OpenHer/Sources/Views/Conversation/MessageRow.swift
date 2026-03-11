import SwiftUI

/// Typography-based message row — NO bubbles.
/// Her messages: left-aligned, deep warm color.
/// Your messages: right-aligned, lighter warm gray.
/// Timestamp shown on hover. Retry button on failed sends.
struct MessageRow: View {
    let message: ChatMessage
    var onRetry: (() -> Void)?

    @State private var isHovering = false

    private var isUser: Bool { message.role == .user }
    private var isFailed: Bool { message.sendStatus == .failed }

    var body: some View {
        VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
            HStack(alignment: .top, spacing: 0) {
                if isUser {
                    Spacer(minLength: 80)
                }

                VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
                    messageContent

                    // Failed indicator + retry
                    if isFailed {
                        HStack(spacing: 4) {
                            Image(systemName: "exclamationmark.circle")
                                .font(.system(size: 11))
                                .foregroundStyle(Paper.coral)
                            Text("发送失败")
                                .font(Paper.tinyFont)
                                .foregroundStyle(Paper.coral)
                            Button("重试") {
                                onRetry?()
                            }
                            .font(Paper.tinyFont)
                            .foregroundStyle(Paper.ink)
                            .buttonStyle(.plain)
                        }
                    }
                }

                if !isUser {
                    Spacer(minLength: 80)
                }
            }

            // Hover timestamp — only visible on mouse hover
            if isHovering {
                Text(formattedTime)
                    .font(Paper.tinyFont)
                    .foregroundStyle(Paper.faint)
                    .transition(.opacity)
            }
        }
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) {
                isHovering = hovering
            }
        }
    }

    // MARK: - Timestamp Formatting

    private var formattedTime: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: message.timestamp)
    }

    // MARK: - Message Content

    @ViewBuilder
    private var messageContent: some View {
        switch message.modality {
        case "表情":
            Text(message.content)
                .font(.system(size: 40))

        case "照片":
            VStack(alignment: .leading, spacing: 8) {
                RoundedRectangle(cornerRadius: 4)
                    .strokeBorder(Paper.ink, lineWidth: 0.5)
                    .frame(width: 200, height: 150)
                    .background(Paper.faint.opacity(0.1))
                    .overlay(
                        Image(systemName: "photo")
                            .foregroundStyle(Paper.faint)
                    )

                if !message.content.isEmpty {
                    Text(message.content)
                        .font(Paper.bodyFont)
                        .foregroundStyle(isUser ? Paper.yourText : Paper.herText)
                }
            }

        case "语音":
            HStack(spacing: 8) {
                Image(systemName: "play.circle")
                    .font(.system(size: 20))
                    .foregroundStyle(Paper.ink)

                HStack(spacing: 2) {
                    ForEach(0..<20, id: \.self) { i in
                        RoundedRectangle(cornerRadius: 1)
                            .fill(Paper.coral)
                            .frame(
                                width: 2,
                                height: CGFloat.random(in: 4...16)
                            )
                    }
                }

                Text("0:15")
                    .font(Paper.freqFont)
                    .foregroundStyle(Paper.coral)
            }

        default:
            Text(message.content)
                .font(Paper.bodyFont)
                .foregroundStyle(isUser ? Paper.yourText : Paper.herText)
                .textSelection(.enabled)
                .lineSpacing(4)
                .opacity(isFailed ? 0.5 : 1.0)
        }
    }
}
