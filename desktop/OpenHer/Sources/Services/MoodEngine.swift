import Foundation

/// Maps engine status to ambient Mood.
/// The user never sees these numbers — they _feel_ them.
enum MoodEngine {
    static func computeMood(from status: EngineStatus) -> Mood {
        let connection = status.driveState?["connection"] ?? 0.5
        let temperature = status.temperature ?? 0.5
        let frustration = status.frustration ?? 0.0
        let depth = status.relationship?.depth ?? 0.0

        // Priority: hurt > excited > intimate > warm > cool > calm
        if frustration > 0.7 {
            return .hurt
        }
        if temperature > 0.7 {
            return .excited
        }
        if depth > 0.6 {
            return .intimate
        }
        if connection > 0.65 {
            return .warm
        }
        if connection < 0.35 {
            return .cool
        }
        return .calm
    }
}
