import SwiftUI

/// Typography-based message row — NO bubbles.
/// Her messages: left-aligned, deep warm color.
/// Your messages: right-aligned, lighter warm gray.
/// Timestamp shown on hover. Retry button on failed sends.
struct MessageRow: View {
    let message: ChatMessage
    let serverURL: String
    var onRetry: (() -> Void)?
    var onImageTap: ((URL) -> Void)?

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
        VStack(alignment: .leading, spacing: 8) {
            // Layer 1: Image — render if imageURL is present (any modality)
            if let urlStr = message.imageURL,
               let url = URL(string: serverURL + urlStr) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(maxWidth: 200)
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                            .onTapGesture { onImageTap?(url) }
                            .cursor(.pointingHand)
                    case .failure:
                        photoPlaceholder
                    case .empty:
                        ProgressView()
                            .frame(width: 200, height: 150)
                    @unknown default:
                        photoPlaceholder
                    }
                }
            }

            // Layer 2: Voice — render if audioData is present
            if message.audioData != nil {
                VoiceMessageView(message: message)
            }

            // Layer 3: Text — render if content is non-empty (skip if voice-only with audio)
            if !message.content.isEmpty && message.audioData == nil {
                if message.modality == "表情" {
                    Text(message.content)
                        .font(.system(size: 40))
                } else {
                    Text(message.content)
                        .font(Paper.bodyFont)
                        .foregroundStyle(isUser ? Paper.yourText : Paper.herText)
                        .textSelection(.enabled)
                        .lineSpacing(4)
                        .opacity(isFailed ? 0.5 : 1.0)
                }
            }
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

// MARK: - Cursor Helper

extension View {
    func cursor(_ cursor: NSCursor) -> some View {
        self.onHover { inside in
            if inside { cursor.push() } else { NSCursor.pop() }
        }
    }
}
