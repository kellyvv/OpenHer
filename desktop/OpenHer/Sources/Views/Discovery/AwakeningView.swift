import SwiftUI
import AVFoundation

/// Awakening transition — video → sci-fi initialization → conversation.
///
/// Transition strategy:
/// - Video stays visible as background while init sequence fades in on top
/// - Init text uses typewriter character-by-character reveal
/// - Init text fades out before transitioning to conversation
struct AwakeningView: View {
    let persona: Persona
    @EnvironmentObject var appState: AppState

    // Video
    @State private var player: AVPlayer?
    @State private var hasVideo: Bool = false
    @State private var videoReady: Bool = false

    // Init sequence
    @State private var showInitSequence: Bool = false
    @State private var dimAmount: Double = 0
    @State private var initPhase: Int = 0
    @State private var typedTexts: [String] = []
    @State private var initComplete: Bool = false
    @State private var fadingOut: Bool = false

    // Name
    @State private var nameOpacity: Double = 0

    /// Persona-specific initialization steps
    private var initSteps: [String] {
        let mbti = persona.mbti ?? "UNKNOWN"
        let desc = persona.description ?? "标准模式"
        let tagStr = persona.tags.prefix(3).map { "#\($0)" }.joined(separator: " ")

        return [
            "正在初始化神经通路...",
            "灌入记忆数据...",
            "设定性格参数: \(mbti)",
            "情感基线校准: \(desc)",
            "共振标签注入: \(tagStr)",
            "启动意识核心...",
        ]
    }

    var body: some View {
        ZStack {
            // === Layer 0: Base persona image (continuity from PersonaCard) ===
            personaBaseImage
                .ignoresSafeArea()

            // === Layer 1: Video — crossfades in slowly over base image ===
            if hasVideo, let player = player {
                AVPlayerRepresentable(player: player)
                    .ignoresSafeArea()
                    .opacity(videoReady ? 1 : 0)
                    .animation(.easeInOut(duration: 0.8), value: videoReady)
            }

            // === Layer 2: Gradual dim overlay — bridges video into init ===
            Paper.background
                .opacity(dimAmount)
                .ignoresSafeArea()
                .animation(.easeInOut(duration: 1.2), value: dimAmount)

            // === Layer 3: Init sequence text ===
            if showInitSequence {
                initSequenceView
                    .opacity(fadingOut ? 0 : 1)
                    .animation(.easeOut(duration: 0.8), value: fadingOut)
            }
        }
        .onAppear {
            setupAwakening()
        }
        .onDisappear {
            cleanupPlayer()
        }
    }

    // MARK: - Base Image

    @ViewBuilder
    private var personaBaseImage: some View {
        if let url = Bundle.module.url(forResource: persona.personaId, withExtension: "png", subdirectory: "cabinets"),
           let nsImage = NSImage(contentsOf: url) {
            GeometryReader { geo in
                Image(nsImage: nsImage)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(width: geo.size.width, height: geo.size.height)
                    .clipped()
            }
        } else {
            Paper.background
        }
    }

    // MARK: - Init Sequence View

    private var initSequenceView: some View {
        VStack(spacing: 0) {
            Spacer()

            // Persona name
            Text(persona.displayName)
                .font(.system(size: 36, weight: .semibold, design: .serif))
                .foregroundStyle(Paper.herText)
                .opacity(nameOpacity)
                .padding(.bottom, 8)

            if let mbti = persona.mbti {
                Text(mbti)
                    .font(.system(size: 13, weight: .medium, design: .monospaced))
                    .foregroundStyle(Paper.faint)
                    .opacity(nameOpacity)
                    .padding(.bottom, 36)
            }

            // Terminal log — typewriter style
            VStack(alignment: .leading, spacing: 12) {
                ForEach(0..<typedTexts.count, id: \.self) { i in
                    HStack(spacing: 10) {
                        // Checkmark for completed, spinner for current
                        if i < typedTexts.count - 1 || initComplete {
                            Image(systemName: "checkmark")
                                .font(.system(size: 9, weight: .bold))
                                .foregroundStyle(Paper.coral)
                                .frame(width: 14, height: 14)
                        } else {
                            ProgressView()
                                .scaleEffect(0.45)
                                .frame(width: 14, height: 14)
                        }

                        Text(typedTexts[i])
                            .font(.system(size: 12, weight: .regular, design: .monospaced))
                            .foregroundStyle(Paper.ink.opacity(0.7))
                    }
                }
            }
            .frame(maxWidth: 300, alignment: .leading)

            Spacer().frame(height: 36)

            // "已上线" — final ceremonial line
            if initComplete {
                Text("「\(persona.displayName) 已上线」")
                    .font(.system(size: 16, weight: .medium, design: .serif))
                    .foregroundStyle(Paper.coral)
                    .transition(.opacity)
            }

            Spacer()

            // Breathing dot
            Circle()
                .fill(Paper.coral)
                .frame(width: 6, height: 6)
                .scaleEffect(initPhase % 2 == 0 ? 1.0 : 1.4)
                .opacity(0.5)
                .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: initPhase)

            Spacer().frame(height: 40)
        }
        .padding(.horizontal, 40)
    }

    // MARK: - Setup

    private func setupAwakening() {
        if let videoURL = Bundle.module.url(
            forResource: "\(persona.personaId)_awakening",
            withExtension: "mp4",
            subdirectory: "cabinets"
        ) {
            let asset = AVURLAsset(url: videoURL)
            let playerItem = AVPlayerItem(asset: asset)
            let avPlayer = AVPlayer(playerItem: playerItem)
            self.player = avPlayer
            self.hasVideo = true

            // Start playback immediately (invisible — video buffers first frames)
            avPlayer.play()

            // After a brief buffer, crossfade video in over the static PNG
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                videoReady = true
            }

            // Start init sequence 2s BEFORE video ends —
            // video continues playing underneath, audio fades during typing
            Task {
                let duration = try? await asset.load(.duration)
                if let duration = duration {
                    let durationSec = CMTimeGetSeconds(duration)
                    let overlapStart = max(0, durationSec - 2.0)
                    let overlapTime = CMTime(seconds: overlapStart, preferredTimescale: 600)
                    avPlayer.addBoundaryTimeObserver(
                        forTimes: [NSValue(time: overlapTime)],
                        queue: .main
                    ) {
                        startInitSequence()
                    }
                } else {
                    // Fallback: use end notification if can't get duration
                    NotificationCenter.default.addObserver(
                        forName: .AVPlayerItemDidPlayToEndTime,
                        object: playerItem,
                        queue: .main
                    ) { _ in
                        self.startInitSequence()
                    }
                }
            }
        } else {
            // No video — go to init after a brief pause
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                startInitSequence()
            }
        }
    }

    // MARK: - Init Sequence with Typewriter

    private func startInitSequence() {
        guard !showInitSequence else { return }  // prevent double trigger
        showInitSequence = true

        // Gradually dim the video/background over 1.2s
        dimAmount = 0.88

        // Fade out audio over 3s — extends into typing phase
        fadeOutAudio(duration: 3.0)

        // Animate name appearance
        withAnimation(.easeOut(duration: 0.8)) {
            nameOpacity = 1.0
        }

        // Start typewriter steps after name appears
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            typewriteStep(index: 0)
        }
    }

    /// Gradually reduce video volume over the specified duration
    private func fadeOutAudio(duration: Double = 2.0) {
        guard let player = player else { return }
        let steps = 20
        let interval = duration / Double(steps)

        for i in 1...steps {
            DispatchQueue.main.asyncAfter(deadline: .now() + interval * Double(i)) {
                let volume = max(0, 1.0 - Float(i) / Float(steps))
                player.volume = volume
            }
        }
    }

    private func typewriteStep(index: Int) {
        guard index < initSteps.count else {
            // All steps done — show "已上线"
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                withAnimation(.easeInOut(duration: 0.4)) {
                    initComplete = true
                }
                // Fade out everything, then transition
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                    fadeOutAndTransition()
                }
            }
            return
        }

        initPhase = index + 1
        let fullText = initSteps[index]

        // Add empty string placeholder
        withAnimation(.easeIn(duration: 0.15)) {
            typedTexts.append("")
        }

        // Typewriter: reveal characters one by one
        let chars = Array(fullText)
        for (charIndex, _) in chars.enumerated() {
            let delay = Double(charIndex) * 0.035  // 35ms per character
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
                if typedTexts.count > index {
                    typedTexts[index] = String(chars.prefix(charIndex + 1))
                }
            }
        }

        // After this line finishes typing, pause, then start next
        let typeDuration = Double(chars.count) * 0.035
        let pauseAfter = 0.4  // brief pause between lines
        DispatchQueue.main.asyncAfter(deadline: .now() + typeDuration + pauseAfter) {
            typewriteStep(index: index + 1)
        }
    }

    private func fadeOutAndTransition() {
        // RootView handles the slide-up animation — just switch phase
        appState.completeAwakening()
    }

    private func cleanupPlayer() {
        player?.pause()
        if let item = player?.currentItem {
            NotificationCenter.default.removeObserver(self, name: .AVPlayerItemDidPlayToEndTime, object: item)
        }
        player = nil
    }
}

// MARK: - AVPlayerRepresentable

struct AVPlayerRepresentable: NSViewRepresentable {
    let player: AVPlayer

    func makeNSView(context: Context) -> NSView {
        let view = AVPlayerLayerView()
        view.playerLayer.player = player
        view.playerLayer.videoGravity = .resizeAspectFill
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        guard let layerView = nsView as? AVPlayerLayerView else { return }
        layerView.playerLayer.player = player
    }
}

private class AVPlayerLayerView: NSView {
    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        wantsLayer = true
    }

    override func makeBackingLayer() -> CALayer {
        return AVPlayerLayer()
    }

    var playerLayer: AVPlayerLayer {
        return layer as! AVPlayerLayer
    }

    override func layout() {
        super.layout()
        playerLayer.frame = bounds
    }
}
