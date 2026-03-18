import SwiftUI

/// Full engine state for developer visualization panel.
/// Parsed from the `debug` field in `chat_end` WebSocket messages.
@MainActor
final class EngineDebugState: ObservableObject {
    // ── Neural Network Activations (Plan B) ──
    @Published var inputVector: [Double] = Array(repeating: 0, count: 25)
    @Published var hiddenActivations: [Double] = Array(repeating: 0, count: 24)
    @Published var signals: [String: Double] = [:]

    // ── Context (12D from Critic) ──
    @Published var contextVector: [String: Double] = [:]

    // ── Drives ──
    @Published var driveState: [String: Double] = [:]
    @Published var driveBaseline: [String: Double] = [:]

    // ── Metabolism ──
    @Published var frustration: Double = 0
    @Published var temperature: Double = 0

    // ── Feel Pass ──
    @Published var monologue: String = ""

    // ── Style Memory Recall ──
    @Published var styleRecall: [RecallItem] = []

    // ── Relationship ──
    @Published var relationship: [String: Double] = [:]

    // ── Meta ──
    @Published var reward: Double = 0
    @Published var age: Int = 0
    @Published var turnCount: Int = 0
    @Published var phaseTransition: Bool = false

    /// Monotonically increasing counter — incremented on every update() call.
    /// Used by EngineWebPanel as injection key to avoid cross-session key collisions.
    private(set) var updateSeq: Int = 0

    // ── Animation State (frontend-driven) ──
    // NOTE: animPulse is NOT used with withAnimation — Canvas reads wall-clock time directly.
    @Published var isComputing: Bool = false
    /// Wall-clock time when the current forward pass started. Canvas computes progress itself.
    var computeStartTime: Date? = nil
    /// How long (seconds) the forward-pass animation runs (matches web ~3s).
    let computeDuration: Double = 3.0

    struct RecallItem: Identifiable {
        let id = UUID()
        let text: String
        let distance: Double
        let mass: Double
    }

    /// Update from a `debug` JSON dictionary (from chat_end WebSocket message).
    func update(from json: [String: Any]) {
        if let iv = json["input_vector"] as? [Double] { inputVector = iv }
        if let ha = json["hidden_activations"] as? [Double] { hiddenActivations = ha }
        if let sig = json["signals"] as? [String: Double] { signals = sig }
        if let ctx = json["context_vector"] as? [String: Double] { contextVector = ctx }
        if let ds = json["drive_state"] as? [String: Double] { driveState = ds }
        if let db = json["drive_baseline"] as? [String: Double] { driveBaseline = db }
        if let f = json["frustration"] as? Double { frustration = f }
        if let t = json["temperature"] as? Double { temperature = t }
        if let m = json["monologue"] as? String { monologue = m }
        if let r = json["reward"] as? Double { reward = r }
        if let a = json["age"] as? Int { age = a }
        if let tc = json["turn_count"] as? Int { turnCount = tc }
        if let pt = json["phase_transition"] as? Bool { phaseTransition = pt }

        if let rel = json["relationship"] as? [String: Double] { relationship = rel }

        // Parse style recall
        if let recalls = json["style_recall"] as? [[String: Any]] {
            styleRecall = recalls.compactMap { item in
                guard let text = item["text"] as? String,
                      let dist = item["distance"] as? Double else { return nil }
                return RecallItem(text: text, distance: dist, mass: item["mass"] as? Double ?? 1.0)
            }
        }

        // Advance injection key — must happen before triggerComputeAnimation
        updateSeq += 1

        // Trigger compute animation
        triggerComputeAnimation()
    }

    /// Kick off compute animation — Canvas reads wall-clock time, no SwiftUI animation needed.
    private func triggerComputeAnimation() {
        computeStartTime = Date()
        isComputing = true
        DispatchQueue.main.asyncAfter(deadline: .now() + computeDuration + 0.1) { [weak self] in
            self?.isComputing = false
            self?.computeStartTime = nil
        }
    }

    /// Inject mock data and fire compute animation — for demo/dev preview without backend.
    func triggerDemo() {
        guard !isComputing else { return }
        var rng: UInt64 = UInt64(Date().timeIntervalSince1970 * 1000)
        func r() -> Double {
            rng = rng &* 6364136223846793005 &+ 1442695040888963407
            return Double(rng >> 33) / Double(1 << 31)
        }
        // Random input vector
        inputVector = (0..<25).map { _ in r() * 2 - 1 }
        // Random hidden activations (tanh range -1…1)
        hiddenActivations = (0..<24).map { _ in tanh(r() * 3 - 1.5) }
        // Random signals 0…1
        let names = ["directness","vulnerability","playfulness","initiative","depth","warmth","defiance","curiosity"]
        signals = Dictionary(uniqueKeysWithValues: names.map { ($0, 0.25 + r()*0.5) })
        // Random drives
        let driveNames = ["connection","novelty","expression","safety","play"]
        driveState    = Dictionary(uniqueKeysWithValues: driveNames.map { ($0, 0.2 + r()*0.6) })
        driveBaseline = Dictionary(uniqueKeysWithValues: driveNames.map { ($0, 0.3 + r()*0.4) })
        frustration = r() * 1.2
        temperature = 0.05 + r() * 0.25
        turnCount  += 1
        updateSeq  += 1
        triggerComputeAnimation()
    }
}
