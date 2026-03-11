import SwiftUI

/// Mood states — mapped from EngineStatus drives.
/// Now generates Paper-themed gradients instead of Her-color gradients.
enum Mood: String, CaseIterable {
    case calm, warm, cool, excited, hurt, intimate

    /// Background gradient colors — Paper theme
    var backgroundGradient: [Color] {
        // Not used for gradients anymore — Paper uses flat paper background.
        // These colors retained for frequency indicator dot position only.
        switch self {
        case .calm:     return [Paper.background, Paper.background]
        case .warm:     return [Paper.background, Paper.background]
        case .cool:     return [Paper.background, Paper.background]
        case .excited:  return [Paper.background, Paper.background]
        case .hurt:     return [Paper.background, Paper.background]
        case .intimate: return [Paper.background, Paper.background]
        }
    }

    /// Animation tempo (seconds per cycle)
    var animationTempo: Double {
        switch self {
        case .calm:     return 4.0
        case .warm:     return 3.0
        case .cool:     return 5.0
        case .excited:  return 1.5
        case .hurt:     return 6.0
        case .intimate: return 3.5
        }
    }
}
