import Foundation

/// WebSocket manager handling the /ws/chat protocol.
/// Manages connection lifecycle, message parsing, and streaming.
@MainActor
final class WebSocketManager: ObservableObject {
    private weak var appState: AppState?
    private var webSocketTask: URLSessionWebSocketTask?
    private var sessionId: String?
    private var streamingContent: String = ""

    init(appState: AppState) {
        self.appState = appState
    }

    // MARK: - Connection

    func connect() {
        guard let appState = appState else { return }
        let wsURL = appState.serverURL
            .replacingOccurrences(of: "http://", with: "ws://")
            .replacingOccurrences(of: "https://", with: "wss://")
        guard let url = URL(string: "\(wsURL)/ws/chat") else { return }

        let session = URLSession(configuration: .default)
        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()

        appState.isConnected = true
        listenForMessages()
        print("[WS] Connected to \(url)")
    }

    func disconnect() {
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        appState?.isConnected = false
        print("[WS] Disconnected")
    }

    // MARK: - Send

    func sendChat(content: String, personaId: String, clientId: String) {
        var payload: [String: Any] = [
            "type": "chat",
            "content": content,
            "persona_id": personaId,
            "client_id": clientId,
            "session_id": sessionId as Any,
        ]

        // Attach awakening greeting on first message so backend LLM has context
        if let appState = appState,
           let greetingMsg = appState.messages.first(where: { $0.id == "awakening-greeting" }) {
            payload["greeting"] = greetingMsg.content
        }

        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let text = String(data: data, encoding: .utf8) else { return }

        webSocketTask?.send(.string(text)) { error in
            if let error = error {
                print("[WS] Send error: \(error)")
            }
        }
    }

    /// Notify the server whether the user is actively typing.
    /// This enables message debounce — the server buffers rapid messages
    /// and processes them as one turn once typing stops.
    func sendTypingIndicator(active: Bool) {
        let payload: [String: Any] = [
            "type": "typing",
            "active": active,
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let text = String(data: data, encoding: .utf8) else { return }

        webSocketTask?.send(.string(text)) { error in
            if let error = error {
                print("[WS] Typing indicator send error: \(error)")
            }
        }
    }

    // MARK: - Receive

    private func listenForMessages() {
        webSocketTask?.receive { [weak self] result in
            Task { @MainActor in
                switch result {
                case .success(let message):
                    switch message {
                    case .string(let text):
                        self?.handleMessage(text)
                    default:
                        break
                    }
                    // Continue listening
                    self?.listenForMessages()

                case .failure(let error):
                    print("[WS] Receive error: \(error)")
                    self?.appState?.isConnected = false
                    // Auto-reconnect after 3 seconds
                    try? await Task.sleep(for: .seconds(3))
                    self?.connect()
                }
            }
        }
    }

    private func handleMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else { return }

        switch type {
        case "chat_start":
            sessionId = json["session_id"] as? String
            streamingContent = ""
            appState?.isTyping = true

        case "chat_chunk":
            if let chunk = json["content"] as? String {
                streamingContent += chunk
                updateStreamingMessage()
            }

        case "chat_end":
            appState?.isTyping = false
            let reply = json["reply"] as? String ?? streamingContent
            let modality = json["modality"] as? String ?? "文字"

            // Parse engine status for mood system
            if let raw = json["relationship"] {
                print("[chat_end] relationship raw: \(raw)")
            } else {
                print("[chat_end] ⚠️ no 'relationship' key in json. Keys: \(json.keys.sorted())")
            }
            if let pm = json["personal_memories"] {
                print("[chat_end] personal_memories: \(pm)")
            }
            let engineStatus = parseEngineStatus(json)
            let imageURL = json["image_url"] as? String

            // Finalize the assistant message
            finalizeMessage(reply: reply, modality: modality, imageURL: imageURL, engineStatus: engineStatus)

            // Update mood from engine status
            if let status = engineStatus {
                let newMood = MoodEngine.computeMood(from: status)
                appState?.currentMood = newMood

                // Per-turn signals for frequency indicator
                let valence = status.relationship?.valence ?? 0.0
                let reward = json["last_reward"] as? Double ?? 0.0
                let temp = status.temperature ?? 0.0
                appState?.valence = valence
                appState?.lastReward = reward
                appState?.emotionTemperature = temp

                // Crystal detection
                if let memories = json["personal_memories"] as? Int {
                    if memories > (appState?.crystalCount ?? 0) {
                        print("[crystal] ✨ new crystal! \(appState?.crystalCount ?? 0) → \(memories)")
                    }
                    appState?.crystalCount = memories
                }

                print("[mood] valence=\(valence) reward=\(reward) temp=\(temp) → \(newMood)")
            }

        case "silence":
            // Persona chose not to reply — dismiss typing bubble, show nothing
            appState?.isTyping = false
            streamingContent = ""
            // Remove any streaming placeholder that was created during Express
            if let idx = appState?.messages.lastIndex(where: { $0.id == "streaming_current" }) {
                appState?.messages.remove(at: idx)
            }
            print("[silence] 🤫 persona chose silence")

        case "proactive":
            let content = json["content"] as? String ?? ""
            let modality = json["modality"] as? String ?? "文字"
            let msg = ChatMessage(
                role: .assistant,
                content: content,
                modality: modality
            )
            appState?.messages.append(msg)

            // Send native notification
            NotificationService.shared.sendNotification(
                title: appState?.selectedPersona?.name ?? "OpenHer",
                body: content
            )

        case "error":
            let errContent = json["content"] as? String ?? "Unknown error"
            print("[WS] Error: \(errContent)")
            appState?.isTyping = false

        case "tts_audio":
            // Decode base64 audio and attach to last assistant message
            if let audioBase64 = json["audio"] as? String,
               let audioData = Data(base64Encoded: audioBase64) {
                let format = json["format"] as? String ?? "wav"
                print("[WS] tts_audio received: \(audioData.count) bytes (\(format))")
                // Find the last assistant message and attach audio
                if let idx = appState?.messages.lastIndex(where: { $0.role == .assistant }) {
                    appState?.messages[idx].audioData = audioData
                }
            }

        default:
            break
        }
    }

    // MARK: - Streaming helpers

    private func updateStreamingMessage() {
        guard let appState = appState else { return }

        let streamingId = "streaming_current"
        if let idx = appState.messages.lastIndex(where: { $0.id == streamingId }) {
            appState.messages[idx].content = streamingContent
        } else {
            let msg = ChatMessage(
                id: streamingId,
                role: .assistant,
                content: streamingContent,
                modality: "文字"
            )
            appState.messages.append(msg)
        }
    }

    private func finalizeMessage(reply: String, modality: String, imageURL: String? = nil, engineStatus: EngineStatus?) {
        guard let appState = appState else { return }

        let streamingId = "streaming_current"
        if let idx = appState.messages.lastIndex(where: { $0.id == streamingId }) {
            appState.messages[idx] = ChatMessage(
                id: UUID().uuidString,
                role: .assistant,
                content: reply,
                modality: modality,
                imageURL: imageURL,
                engineStatus: engineStatus
            )
        } else {
            let msg = ChatMessage(
                role: .assistant,
                content: reply,
                modality: modality,
                imageURL: imageURL,
                engineStatus: engineStatus
            )
            appState.messages.append(msg)
        }
        streamingContent = ""
    }

    // MARK: - Engine status parsing

    private func parseEngineStatus(_ json: [String: Any]) -> EngineStatus? {
        let dominantDrive = json["dominant_drive"] as? String
        let temperature = json["temperature"] as? Double
        let frustration = json["frustration"] as? Double
        let modality = json["modality"] as? String
        let turnCount = json["turn_count"] as? Int
        let driveState = json["drive_state"] as? [String: Double]

        var relationship: RelationshipState? = nil
        if let rel = json["relationship"] as? [String: Any] {
            relationship = RelationshipState(
                depth: rel["depth"] as? Double,
                trust: rel["trust"] as? Double,
                valence: rel["valence"] as? Double
            )
        }

        return EngineStatus(
            dominantDrive: dominantDrive,
            temperature: temperature,
            frustration: frustration,
            modality: modality,
            turnCount: turnCount,
            relationship: relationship,
            driveState: driveState
        )
    }
}
