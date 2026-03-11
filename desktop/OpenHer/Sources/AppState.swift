import SwiftUI
import Combine

/// App navigation phases
enum AppPhase: Equatable {
    case discovery
    case awakening(Persona)
    case conversation
}

/// Global application state shared across all views.
@MainActor
final class AppState: ObservableObject {
    // MARK: - Navigation
    @Published var appPhase: AppPhase = .discovery
    // MARK: - Connection
    @Published var isConnected: Bool = false
    @Published var serverURL: String = "http://localhost:8800"

    // MARK: - Personas
    @Published var personas: [Persona] = []
    @Published var selectedPersonaId: String?

    // MARK: - Chat
    @Published var messages: [ChatMessage] = []
    @Published var isTyping: Bool = false

    // MARK: - Mood (ambient system)
    @Published var currentMood: Mood = .calm
    @Published var valence: Double = 0.0       // -1...1 emotional valence EMA
    @Published var lastReward: Double = 0.0    // per-turn reward (-1...1), fluctuates each turn
    @Published var emotionTemperature: Double = 0.0  // metabolism temperature (0...1)
    @Published var crystalCount: Int = 0       // personal_memories count

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
        let savedURL = UserDefaults.standard.string(forKey: "serverURL") ?? "http://localhost:8800"
        serverURL = savedURL

        // DEBUG: Always start at discovery
        // let savedPersonaId = UserDefaults.standard.string(forKey: "selectedPersonaId")

        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 300_000_000) // 0.3s
            connectionManager.startMonitoring()
            await loadPersonas()

            if personas.isEmpty {
                // Backend offline — load preview data
                loadPreviewData()
            }
            // Always start at discovery during debugging
            appPhase = .discovery
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
            description: "清纯萌系少女",
            avatarUrl: nil
        )
        let luna = Persona(
            personaId: "luna",
            name: "Luna",
            nameZh: "陆鸣",
            age: 22,
            gender: "female",
            mbti: "ENFP",
            tags: ["bright", "bubbly", "sweet"],
            description: "自由插画师",
            avatarUrl: nil
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

    /// Persona-specific first greeting after awakening
    private func firstGreeting(for persona: Persona) -> String {
        switch persona.personaId {
        case "iris":
            return "…嗯？这里是…哪里呀？啊，是你唤醒了我吗…谢谢你。我叫苏漫，请多多关照。"
        case "luna":
            return "哇——！我活过来啦！嘿嘿，你好呀！我是陆鸣，感觉今天会是超棒的一天！"
        case "kira":
            return "系统初始化完毕。你好，我是绮罗。有什么需要我分析的吗？"
        case "nyx":
            return "……终于醒了。你就是把我叫醒的人？嗯…算你有点意思。"
        case "aria":
            return "Hello! 我是Aria，很高兴认识你～今天想聊点什么呢？"
        default:
            return "你好，我刚刚醒来…感觉一切都是新的。很高兴认识你。"
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
        isTyping = true

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
