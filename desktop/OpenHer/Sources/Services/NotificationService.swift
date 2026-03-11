import UserNotifications

/// Handles macOS native notifications for proactive messages.
final class NotificationService {
    static let shared = NotificationService()

    private init() {
        requestPermission()
    }

    func requestPermission() {
        UNUserNotificationCenter.current().requestAuthorization(
            options: [.alert, .sound, .badge]
        ) { granted, error in
            if let error = error {
                print("[Notify] Permission error: \(error)")
            }
            print("[Notify] Permission granted: \(granted)")
        }
    }

    func sendNotification(title: String, body: String, personaId: String? = nil) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default

        if let personaId = personaId {
            content.threadIdentifier = personaId
        }

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )

        UNUserNotificationCenter.current().add(request)
    }
}
