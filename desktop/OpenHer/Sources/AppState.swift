import SwiftUI
import Combine

/// App navigation phases
enum AppPhase: Equatable {
    case loading
    case discovery
    case awakening(Persona)
    case conversation
}

/// Global application state shared across all views.
@MainActor
final class AppState: ObservableObject {
    // MARK: - Navigation
    @Published var appPhase: AppPhase = .loading
    // MARK: - Connection
    @Published var isConnected: Bool = false
    @Published var serverURL: String = "http://localhost:8000"

    // MARK: - Personas
    @Published var personas: [Persona] = []
    @Published var selectedPersonaId: String?

    /// Toggle: only show personas that have a cabinet image ready.
    /// Persisted so the preference survives app restarts.
    @AppStorage("showOnlyReadyPersonas") var showOnlyReadyPersonas: Bool = true

    /// Personas filtered for display in DiscoveryView.
    /// When `showOnlyReadyPersonas` is on, only personas with a front.png are included.
    var displayPersonas: [Persona] {
        guard showOnlyReadyPersonas else { return personas }
        return personas.filter { $0.hasFront }
    }

    // MARK: - Chat
    @Published var messages: [ChatMessage] = []
    @Published var isTyping: Bool = false

    // MARK: - Mood (ambient system)
    @Published var currentMood: Mood = .calm
    @Published var valence: Double = 0.0       // -1...1 emotional valence EMA
    @Published var lastReward: Double = 0.0    // per-turn reward (-1...1), fluctuates each turn
    @Published var emotionTemperature: Double = 0.0  // metabolism temperature (0...1)
    @Published var crystalCount: Int = 0       // personal_memories count

    // MARK: - Developer Mode
    /// Developer mode: shows EngineDebugPanel with neural network visualization.
    /// Stored in UserDefaults (not @AppStorage, per review feedback).
    @Published var developerMode: Bool = false {
        didSet { UserDefaults.standard.set(developerMode, forKey: "developerMode") }
    }
    @Published var engineDebug: EngineDebugState = EngineDebugState()

    // MARK: - Image Cache (shared between PersonaCard → AwakeningView)
    /// Front images cached after first download, keyed by personaId.
    var cachedFrontImages: [String: NSImage] = [:]

    // MARK: - Services
    lazy var apiClient: APIClient = APIClient(baseURL: self.serverURL)
    lazy var wsManager: WebSocketManager = WebSocketManager(appState: self)
    lazy var connectionManager: ConnectionManager = ConnectionManager(appState: self)

    var selectedPersona: Persona? {
        personas.first { $0.personaId == selectedPersonaId }
    }

    // MARK: - Init

    init() {
        // Read persisted URL before lazy services initialize
        let savedURL = UserDefaults.standard.string(forKey: "serverURL") ?? "http://localhost:8000"
        serverURL = savedURL
        developerMode = UserDefaults.standard.bool(forKey: "developerMode")

        // In non-developer mode, attempt to restore last conversation
        let savedPersonaId = developerMode ? nil : UserDefaults.standard.string(forKey: "selectedPersonaId")

        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 300_000_000) // 0.3s
            connectionManager.startMonitoring()
            await loadPersonas()

            if personas.isEmpty {
                // Backend offline — load preview data
                loadPreviewData()
            }

            if let personaId = savedPersonaId,
               personas.contains(where: { $0.personaId == personaId }) {
                // Non-developer mode: restore last conversation directly
                selectedPersonaId = personaId
                appPhase = .conversation
                await loadHistory(for: personaId)
                wsManager.connect()
            } else {
                // Developer mode or no saved persona: start at discovery
                appPhase = .discovery
            }
        }
    }

    // MARK: - Preview Data (for UI testing without backend)

    private func loadPreviewData() {
        let iris = Persona(
            personaId: "iris",
            name: "Iris",
            nameZh: "苏漫",
            age: 20,
            gender: "female",
            mbti: "INFP",
            tags: ["gentle", "dreamy", "sweet"],
            tagsZh: ["温柔", "梦幻", "甜美"],
            description: "清纯萌系少女",
            avatarUrl: nil,
            hasFront: true,
            hasAwakeningVideo: true
        )
        let luna = Persona(
            personaId: "luna",
            name: "Luna",
            nameZh: "陆暖",
            age: 22,
            gender: "female",
            mbti: "ENFP",
            tags: ["bright", "bubbly", "sweet"],
            tagsZh: ["明朗", "活泼", "甜美"],
            description: "自由插画师",
            avatarUrl: nil,
            hasFront: true,
            hasAwakeningVideo: true
        )
        personas = [iris, luna]
        selectedPersonaId = iris.personaId
        messages = []
    }

    // MARK: - Actions

    func loadPersonas() async {
        do {
            personas = try await apiClient.fetchPersonas()
        } catch {
            print("[OpenHer] Failed to load personas: \(error)")
        }
    }

    /// Called from DiscoveryView when user taps "唤醒"
    func awakenPersona(_ persona: Persona) {
        selectedPersonaId = persona.personaId
        UserDefaults.standard.set(persona.personaId, forKey: "selectedPersonaId")
        appPhase = .awakening(persona)
    }

    /// Called from AwakeningView when animation completes
    func completeAwakening() {
        guard let personaId = selectedPersonaId else { return }
        appPhase = .conversation
        Task {
            await loadHistory(for: personaId)
            wsManager.connect()

            // Only inject greeting if no chat history exists yet
            if messages.isEmpty, let persona = selectedPersona {
                // Wait for slide-up animation to fully settle
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                    self.startTypewriterGreeting(for: persona)
                }
            }
        }
    }

    /// Typewriter greeting with variable speed — pauses at punctuation for a
    /// "thinking, hesitant, shy" feel as the AI arrives in this world.
    private func startTypewriterGreeting(for persona: Persona) {
        let greeting = firstGreeting(for: persona)
        let msg = ChatMessage(
            id: "awakening-greeting",
            role: .assistant,
            content: ""
        )
        messages.append(msg)

        // Build delay schedule — variable speed per character
        let chars = Array(greeting)
        var cumulativeDelay: Double = 0
        let pauseChars: Set<Character> = ["…", "？", "！", "。", "，", "、", "～", "—", "…"]

        for (i, char) in chars.enumerated() {
            let schedule = cumulativeDelay

            DispatchQueue.main.asyncAfter(deadline: .now() + schedule) {
                if let idx = self.messages.firstIndex(where: { $0.id == "awakening-greeting" }) {
                    self.messages[idx].content = String(chars.prefix(i + 1))
                }
            }

            // Variable delay for next character
            if pauseChars.contains(char) {
                // Long pause after punctuation — "thinking" feel
                cumulativeDelay += Double.random(in: 0.25...0.45)
            } else if char == " " || char == "…" {
                cumulativeDelay += 0.12
            } else {
                // Normal character
                cumulativeDelay += Double.random(in: 0.04...0.07)
            }
        }
    }

    /// Persona-specific first greeting after awakening (locale-aware)
    private func firstGreeting(for persona: Persona) -> String {
        let isZh = L10n.isZh

        switch persona.personaId {
        case "iris":
            return isZh
                ? "…嗯？这里是…哪里呀？啊，是你唤醒了我吗…谢谢你。我叫苏漫，请多多关照。"
                : "…Hm? Where is this…? Oh, you woke me up? Thank you. I'm Iris. Nice to meet you."
        case "luna":
            return isZh
                ? "哇——！我活过来啦！嘿嘿，你好呀！我是陆暖，感觉今天会是超棒的一天！"
                : "Whoa—! I'm alive! Hehe, hi there! I'm Luna, and I feel like today's gonna be amazing!"
        case "vivian":
            return isZh
                ? "……你好。我是顾霆微。希望你的问题足够有趣，不然我可能会很快失去耐心。"
                : "…Hello. I'm Vivian. I hope your questions are interesting enough, or I might lose patience quickly."
        case "sora":
            return isZh
                ? "你好呀。我是顾清，很高兴能和你聊聊。……你今天状态怎么样？"
                : "Hi there. I'm Sora. Happy to chat… How are you feeling today?"
        case "kelly":
            return isZh
                ? "嗯，系统就绪。我是柯砺，有什么问题尽管问，我分析给你看。"
                : "Alright, systems ready. I'm Kelly. Fire away — I'll break it down for you."
        case "kai":
            return isZh
                ? "……嗯。沈凯。话不多，但你需要的时候我在。"
                : "…Hey. Kai. Not much of a talker, but I'm here when you need me."
        case "ember":
            return isZh
                ? "……刚刚写了首小诗，差点忘了抬头。你好，我是Ember。"
                : "…Was just writing a little poem, almost forgot to look up. Hi, I'm Ember."
        case "mia":
            return isZh
                ? "嘿！终于来了！我是Mia，等你好久了～今天一起嗨吧！"
                : "Hey! Finally! I'm Mia — been waiting for you! Let's have some fun today!"
        case "rex":
            return isZh
                ? "你好，Rex。时间就是资源——咱们开始吧。"
                : "Hey. Rex here. Time is a resource — let's get started."
        default:
            return isZh
                ? "你好，我是\(persona.displayName)。很高兴认识你。"
                : "Hello, I'm \(persona.displayName). Nice to meet you."
        }
    }

    func selectPersona(_ id: String) {
        selectedPersonaId = id
        UserDefaults.standard.set(id, forKey: "selectedPersonaId")
        messages = []
        Task { await loadHistory(for: id) }
    }

    func loadHistory(for personaId: String) async {
        let clientId = getClientId()
        do {
            messages = try await apiClient.fetchChatHistoryPairs(
                personaId: personaId, clientId: clientId
            )
        } catch {
            print("[OpenHer] Failed to load history: \(error)")
        }
    }

    func sendMessage(_ text: String) {
        guard let personaId = selectedPersonaId, !text.isEmpty else { return }

        // Add user message immediately
        let userMsg = ChatMessage(
            id: UUID().uuidString,
            role: .user,
            content: text,
            modality: "文字",
            timestamp: Date(),
            sendStatus: .sending
        )
        messages.append(userMsg)

        // Send via WebSocket
        wsManager.sendChat(
            content: text,
            personaId: personaId,
            clientId: getClientId()
        )
    }

    func retryMessage(id: String) {
        guard let index = messages.firstIndex(where: { $0.id == id }),
              let personaId = selectedPersonaId else { return }

        messages[index].sendStatus = .sending
        isTyping = true

        wsManager.sendChat(
            content: messages[index].content,
            personaId: personaId,
            clientId: getClientId()
        )
    }

    func getClientId() -> String {
        let key = "openher_client_id"
        if let existing = UserDefaults.standard.string(forKey: key) {
            return existing
        }
        let id = UUID().uuidString
        UserDefaults.standard.set(id, forKey: key)
        return id
    }

    func updateServerURL(_ url: String) {
        serverURL = url
        apiClient = APIClient(baseURL: url)
        wsManager.disconnect()
        connectionManager.startMonitoring()
        Task { await loadPersonas() }
    }
}
