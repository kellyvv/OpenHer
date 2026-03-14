import SwiftUI

/// Voice message player — play/pause button, waveform, duration.
/// Falls back to text if audio data is missing (e.g. TTS failure).
struct VoiceMessageView: View {
    let message: ChatMessage
    @ObservedObject private var player = AudioPlayerManager.shared

    private var isThisPlaying: Bool {
        player.playingMessageId == message.id && player.isPlaying
    }

    private var audioDuration: TimeInterval {
        if let data = message.audioData {
            return AudioPlayerManager.duration(of: data)
        }
        return 0
    }

    var body: some View {
        if message.audioData == nil && !message.content.isEmpty {
            // Fallback: show text when audio is unavailable
            Text(message.content)
                .font(Paper.bodyFont)
                .foregroundStyle(Paper.herText)
                .textSelection(.enabled)
                .lineSpacing(4)
        } else {
            voicePlayer
        }
    }

    private var voicePlayer: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 10) {
                // Play / Pause button
                Button(action: playTapped) {
                    Image(systemName: isThisPlaying ? "pause.circle.fill" : "play.circle.fill")
                        .font(.system(size: 28))
                        .foregroundStyle(message.audioData != nil ? Paper.coral : Paper.faint)
                }
                .buttonStyle(.plain)
                .disabled(message.audioData == nil)

                // Waveform bars
                HStack(spacing: 2) {
                    ForEach(0..<20, id: \.self) { i in
                        let barProgress = Double(i) / 20.0
                        let highlighted = player.playingMessageId == message.id && barProgress < player.progress
                        RoundedRectangle(cornerRadius: 1)
                            .fill(highlighted ? Paper.coral : Paper.coral.opacity(0.35))
                            .frame(
                                width: 2,
                                height: waveformHeight(for: i)
                            )
                            .animation(.easeInOut(duration: 0.15), value: highlighted)
                    }
                }

                // Duration
                Text(formatDuration(audioDuration))
                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                    .foregroundStyle(Paper.coral)
            }
        }
    }

    private func playTapped() {
        guard let audioData = message.audioData else { return }
        player.play(messageId: message.id, audioData: audioData)
    }

    private func waveformHeight(for index: Int) -> CGFloat {
        // Deterministic pseudo-random waveform based on message id
        let seed = message.id.hashValue &+ index
        let normalized = abs(Double(seed % 100)) / 100.0
        return CGFloat(4 + normalized * 14)
    }

    private func formatDuration(_ seconds: TimeInterval) -> String {
        guard seconds > 0 else { return "0:00" }
        let mins = Int(seconds) / 60
        let secs = Int(seconds) % 60
        return "\(mins):\(String(format: "%02d", secs))"
    }
}

