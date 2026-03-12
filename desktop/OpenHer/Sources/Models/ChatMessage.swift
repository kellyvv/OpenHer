import Foundation

enum MessageRole: String, Codable {
    case user
    case assistant
    case system
}

enum SendStatus: String, Codable {
    case sending
    case sent
    case failed
}

/// A chat message (both user and agent).
struct ChatMessage: Codable, Identifiable {
    let id: String
    let role: MessageRole
    var content: String
    var modality: String
    var imageURL: String?
    var timestamp: Date
    var sendStatus: SendStatus?

    // Engine status (populated from chat_end)
    var engineStatus: EngineStatus?

    init(
        id: String = UUID().uuidString,
        role: MessageRole,
        content: String,
        modality: String = "文字",
        imageURL: String? = nil,
        timestamp: Date = Date(),
        sendStatus: SendStatus? = nil,
        engineStatus: EngineStatus? = nil
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.modality = modality
        self.imageURL = imageURL
        self.timestamp = timestamp
        self.sendStatus = sendStatus
        self.engineStatus = engineStatus
    }
}

/// Engine status from chat_end WebSocket message.
/// Used by MoodEngine to compute ambient UI state — never shown directly.
struct EngineStatus: Codable {
    let dominantDrive: String?
    let temperature: Double?
    let frustration: Double?
    let modality: String?
    let turnCount: Int?
    let relationship: RelationshipState?
    let driveState: [String: Double]?

    enum CodingKeys: String, CodingKey {
        case dominantDrive = "dominant_drive"
        case temperature, frustration, modality
        case turnCount = "turn_count"
        case relationship
        case driveState = "drive_state"
    }
}

struct RelationshipState: Codable {
    let depth: Double?
    let trust: Double?
    let valence: Double?
}
