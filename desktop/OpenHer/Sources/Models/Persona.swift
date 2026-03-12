import Foundation

/// Persona info from /api/personas
struct Persona: Codable, Identifiable, Hashable {
    let personaId: String
    let name: String
    let nameZh: String?
    let age: Int?

    /// Display name: uses Chinese name for Chinese locale, English name otherwise.
    var displayName: String {
        if L10n.isZh, let zh = nameZh { return zh }
        return name
    }
    let gender: String?
    let mbti: String?
    let tags: [String]
    let description: String?
    let avatarUrl: String?

    /// Whether this persona has a front.png (discovery cabinet image)
    let hasFront: Bool
    /// Whether this persona has an awakening.mp4 video
    let hasAwakeningVideo: Bool

    var id: String { personaId }

    enum CodingKeys: String, CodingKey {
        case personaId = "persona_id"
        case name
        case nameZh = "name_zh"
        case age, gender, mbti, tags, description
        case avatarUrl = "avatar_url"
        case hasFront = "has_front"
        case hasAwakeningVideo = "has_awakening_video"
    }
}
