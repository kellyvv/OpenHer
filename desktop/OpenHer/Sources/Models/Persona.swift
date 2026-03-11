import Foundation

/// Persona info from /api/personas
struct Persona: Codable, Identifiable, Hashable {
    let personaId: String
    let name: String
    let nameZh: String?
    let age: Int?

    /// Display name: prefers Chinese name when available.
    var displayName: String { nameZh ?? name }
    let gender: String?
    let mbti: String?
    let tags: [String]
    let description: String?
    let avatarUrl: String?

    var id: String { personaId }

    enum CodingKeys: String, CodingKey {
        case personaId = "persona_id"
        case name
        case nameZh = "name_zh"
        case age, gender, mbti, tags, description
        case avatarUrl = "avatar_url"
    }
}
