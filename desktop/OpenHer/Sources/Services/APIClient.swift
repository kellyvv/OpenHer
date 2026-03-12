import Foundation

/// REST API client for the OpenHer backend.
actor APIClient {
    let baseURL: String

    init(baseURL: String) {
        self.baseURL = baseURL.hasSuffix("/") ? String(baseURL.dropLast()) : baseURL
    }

    // MARK: - Personas

    func fetchPersonas() async throws -> [Persona] {
        let data = try await get("/api/personas")
        let response = try JSONDecoder().decode(PersonasResponse.self, from: data)
        return response.personas
    }

    // MARK: - Chat History

    func fetchChatHistory(personaId: String, clientId: String, limit: Int = 50) async throws -> [ChatMessage] {
        let path = "/api/chat/history/\(personaId)?client_id=\(clientId)&limit=\(limit)"
        let data = try await get(path)

        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard let messagesArray = json?["messages"] as? [[String: Any]] else {
            return []
        }

        return messagesArray.compactMap { dict -> ChatMessage? in
            guard let userMsg = dict["user_msg"] as? String,
                  let agentReply = dict["agent_reply"] as? String else { return nil }

            let modality = dict["modality"] as? String ?? "文字"
            let ts = dict["timestamp"] as? String
            let date = ts.flatMap { ISO8601DateFormatter().date(from: $0) } ?? Date()

            // Each history entry produces two messages
            return nil // Will be handled differently below
        }
    }

    func fetchChatHistoryPairs(personaId: String, clientId: String, limit: Int = 50) async throws -> [ChatMessage] {
        let path = "/api/chat/history/\(personaId)?client_id=\(clientId)&limit=\(limit)"
        let data = try await get(path)

        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard let messagesArray = json?["messages"] as? [[String: Any]] else {
            return []
        }

        var result: [ChatMessage] = []
        for dict in messagesArray {
            guard let userMsg = dict["user_msg"] as? String,
                  let agentReply = dict["agent_reply"] as? String else { continue }

            let modality = dict["modality"] as? String ?? "文字"
            let msgId = dict["id"] as? Int ?? Int.random(in: 1...999999)

            result.append(ChatMessage(
                id: "h_u_\(msgId)",
                role: .user,
                content: userMsg,
                modality: "文字"
            ))
            let imageURL = dict["image_url"] as? String
            result.append(ChatMessage(
                id: "h_a_\(msgId)",
                role: .assistant,
                content: agentReply,
                modality: modality,
                imageURL: imageURL
            ))
        }
        return result
    }

    // MARK: - Status

    func checkStatus() async throws -> Bool {
        let data = try await get("/api/status")
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return json?["status"] as? String == "running"
    }

    // MARK: - Avatar

    nonisolated func avatarURL(for personaId: String) -> URL? {
        URL(string: "\(baseURL)/api/avatar/\(personaId)")
    }

    // MARK: - Internals

    private func get(_ path: String) async throws -> Data {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw APIError.invalidURL
        }
        let (data, response) = try await URLSession.shared.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse,
              200..<300 ~= httpResponse.statusCode else {
            throw APIError.serverError((response as? HTTPURLResponse)?.statusCode ?? 0)
        }
        return data
    }
}

private struct PersonasResponse: Codable {
    let personas: [Persona]
}

enum APIError: Error, LocalizedError {
    case invalidURL
    case serverError(Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .serverError(let code): return "Server error (\(code))"
        }
    }
}
