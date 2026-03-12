import Foundation

/// Lightweight locale helper — returns Chinese or English strings based on system language.
/// Usage: `L10n.str("唤醒", en: "Awaken")`
enum L10n {
    /// Whether the current locale is Chinese
    static let isZh: Bool = {
        let code = Locale.current.language.languageCode?.identifier ?? "en"
        return code == "zh"
    }()

    /// Return zh or en string based on current locale
    static func str(_ zh: String, en: String) -> String {
        isZh ? zh : en
    }
}
