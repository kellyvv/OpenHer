import AVFoundation
import Combine

/// Singleton audio player for voice messages.
/// Manages playback state so MessageRow can show play/pause/progress.
@MainActor
final class AudioPlayerManager: ObservableObject {
    static let shared = AudioPlayerManager()

    @Published var playingMessageId: String? = nil
    @Published var isPlaying: Bool = false
    @Published var progress: Double = 0       // 0...1
    @Published var duration: TimeInterval = 0

    private var player: AVAudioPlayer?
    private var timer: Timer?

    private init() {}

    func play(messageId: String, audioData: Data) {
        // Stop current if different
        if playingMessageId != messageId {
            stop()
        }

        // If same message is playing, toggle pause/resume
        if playingMessageId == messageId, let player = player {
            if player.isPlaying {
                player.pause()
                isPlaying = false
            } else {
                player.play()
                isPlaying = true
                startProgressTimer()
            }
            return
        }

        do {
            player = try AVAudioPlayer(data: audioData)
            player?.prepareToPlay()
            duration = player?.duration ?? 0
            progress = 0
            playingMessageId = messageId
            player?.play()
            isPlaying = true
            startProgressTimer()
        } catch {
            print("[AudioPlayer] Error: \(error)")
            stop()
        }
    }

    func stop() {
        player?.stop()
        player = nil
        timer?.invalidate()
        timer = nil
        playingMessageId = nil
        isPlaying = false
        progress = 0
        duration = 0
    }

    private func startProgressTimer() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self = self, let player = self.player else { return }
                if player.isPlaying {
                    self.progress = player.duration > 0 ? player.currentTime / player.duration : 0
                } else {
                    // Playback finished
                    self.isPlaying = false
                    self.progress = 0
                    self.timer?.invalidate()
                    self.timer = nil
                }
            }
        }
    }

    /// Get duration from audio data without playing
    static func duration(of data: Data) -> TimeInterval {
        guard let player = try? AVAudioPlayer(data: data) else { return 0 }
        return player.duration
    }
}
