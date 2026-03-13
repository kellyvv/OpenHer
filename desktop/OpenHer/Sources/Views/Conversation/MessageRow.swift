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
                            Text(L10n.str("发送失败", en: "Failed"))
                                .font(Paper.tinyFont)
                                .foregroundStyle(Paper.coral)
                            Button(L10n.str("重试", en: "Retry")) {
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

            Text(formattedTime)
                .font(Paper.tinyFont)
                .foregroundStyle(Paper.faint)
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
                if let urlStr = message.imageURL,
                   let url = URL(string: "http://localhost:8800" + urlStr) {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(maxWidth: 200)
                                .clipShape(RoundedRectangle(cornerRadius: 4))
                        case .failure:
                            photoPlaceholder
                        case .empty:
                            ProgressView()
                                .frame(width: 200, height: 150)
                        @unknown default:
                            photoPlaceholder
                        }
                    }
                } else {
                    photoPlaceholder
                }

                if !message.content.isEmpty {
                    Text(message.content)
                        .font(Paper.bodyFont)
                        .foregroundStyle(isUser ? Paper.yourText : Paper.herText)
                }
            }

        case "语音":
            VoiceMessageView(message: message)

        default:
            Text(message.content)
                .font(Paper.bodyFont)
                .foregroundStyle(isUser ? Paper.yourText : Paper.herText)
                .textSelection(.enabled)
                .lineSpacing(4)
                .opacity(isFailed ? 0.5 : 1.0)
        }
    }

    private var photoPlaceholder: some View {
        RoundedRectangle(cornerRadius: 4)
            .strokeBorder(Paper.ink, lineWidth: 0.5)
            .frame(width: 200, height: 150)
            .background(Paper.faint.opacity(0.1))
            .overlay(
                Image(systemName: "photo")
                    .foregroundStyle(Paper.faint)
            )
    }
}
