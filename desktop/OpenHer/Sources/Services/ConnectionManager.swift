import Foundation

/// Periodically checks backend health and reconnects WebSocket.
@MainActor
final class ConnectionManager {
    private weak var appState: AppState?
    private var timer: Timer?

    init(appState: AppState) {
        self.appState = appState
    }

    func startMonitoring() {
        // Initial connection
        Task { await checkAndConnect() }

        // Periodic health check every 30 seconds
        timer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.checkAndConnect()
            }
        }
    }

    func stopMonitoring() {
        timer?.invalidate()
        timer = nil
    }

    private func checkAndConnect() async {
        guard let appState = appState else { return }

        do {
            let running = try await appState.apiClient.checkStatus()
            if running && !appState.isConnected {
                appState.wsManager.connect()
            }
            appState.isConnected = running
        } catch {
            appState.isConnected = false
            print("[Connection] Backend unreachable: \(error.localizedDescription)")
        }
    }
}
