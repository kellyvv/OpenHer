import SwiftUI

/// Paper + Blue + Coral — the analog editorial design system.
/// Every color, font, and dimension traced from the approved concept.
enum Paper {
    // MARK: - Colors

    /// Paper background — warm parchment/linen (matched from reference)
    static let background = Color(red: 240/255, green: 228/255, blue: 210/255)

    /// Blue ink — structure lines, avatar ring, send arrow
    static let ink = Color(red: 45/255, green: 95/255, blue: 138/255)

    /// Avatar ring — soft muted blue-gray (lighter than ink)
    static let ringBlue = Color(red: 140/255, green: 170/255, blue: 195/255)

    /// Coral accent — frequency dot, microphone, FREQ text, emphasis
    static let coral = Color(red: 232/255, green: 93/255, blue: 74/255)

    /// Her text — deep warm dark for her messages
    static let herText = Color(red: 44/255, green: 36/255, blue: 32/255)

    /// Your text — lighter warm gray for user messages
    static let yourText = Color(red: 139/255, green: 129/255, blue: 120/255)

    /// Faint — timestamps, secondary info
    static let faint = Color(red: 180/255, green: 170/255, blue: 158/255)

    // MARK: - Fonts

    /// Her message body
    static let bodyFont = Font.system(.body, design: .default)

    /// User message body
    static let userFont = Font.system(.body, design: .default)

    /// Name label
    static let nameFont = Font.system(size: 16, weight: .semibold, design: .default)

    /// FREQ subtitle
    static let freqFont = Font.system(size: 11, weight: .regular, design: .default)

    /// Input placeholder
    static let inputFont = Font.system(size: 15, design: .default)

    /// Tiny labels (Emotional Attunement text)
    static let tinyFont = Font.system(size: 9, weight: .regular, design: .default)

    // MARK: - Dimensions

    /// Avatar diameter
    static let avatarSize: CGFloat = 64

    /// Avatar ring width
    static let ringWidth: CGFloat = 1.0

    /// Frequency line width
    static let freqLineWidth: CGFloat = 1.0

    /// Frequency dot size
    static let freqDotSize: CGFloat = 8

    /// Input underline height
    static let inputLineHeight: CGFloat = 1.0

    /// Content horizontal padding
    static let hPadding: CGFloat = 36

    /// Message vertical spacing
    static let messageSpacing: CGFloat = 28
}
