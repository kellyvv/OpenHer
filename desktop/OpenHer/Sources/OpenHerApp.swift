import SwiftUI
import AppKit
import Combine

/// Force the app to appear as a regular GUI app + manage window aspect ratio.
@MainActor
class AppDelegate: NSObject, NSApplicationDelegate {
    private var phaseSub: AnyCancellable?

    /// Aspect ratio for Discovery / Awakening (520:960 ≈ 13:24)
    private let discoveryAspect = NSSize(width: 13, height: 24)

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            NSApp.windows.first?.makeKeyAndOrderFront(nil)
        }
    }

    /// Called from OpenHerApp to observe phase changes
    func observePhase(of appState: AppState) {
        // Apply initial lock
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in
            self?.applyAspectLock(for: appState.appPhase)
        }
        // React to phase changes
        phaseSub = appState.$appPhase
            .receive(on: RunLoop.main)
            .sink { [weak self] phase in
                self?.applyAspectLock(for: phase)
            }
    }

    private func applyAspectLock(for phase: AppPhase) {
        guard let window = NSApp.windows.first(where: {
            $0.className.contains("AppKit") || $0.isKeyWindow
        }) ?? NSApp.windows.first else { return }

        switch phase {
        case .discovery, .awakening:
            // Lock aspect ratio — user can resize but proportion stays fixed
            window.contentAspectRatio = discoveryAspect
        case .conversation:
            // Unlock — free resize
            window.contentAspectRatio = NSSize.zero
        }
    }
}

@main
struct OpenHerApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var appState = AppState()

    var body: some Scene {
        // Main window — routes between discovery / awakening / conversation
        WindowGroup {
            RootView()
                .environmentObject(appState)
                .frame(minWidth: 320, minHeight: 480)
                .onAppear {
                    appDelegate.observePhase(of: appState)
                }
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentMinSize)
        .defaultSize(width: 390, height: 720)

        // Menu Bar — coral circle presence
        MenuBarExtra {
            MenuBarView()
                .environmentObject(appState)
        } label: {
            Image(systemName: "circle.fill")
                .symbolRenderingMode(.palette)
                .foregroundStyle(
                    appState.isConnected ? Paper.coral : Color.gray
                )
        }
        .menuBarExtraStyle(.window)

        // Settings
        Settings {
            SettingsView()
                .environmentObject(appState)
        }

        // Developer Mode: Engine Visualization (HTML5 via WKWebView)
        Window("Persona Engine", id: "engine-debug") {
            EngineWebPanel(debugState: appState.engineDebug)
                .environmentObject(appState)
                .frame(minWidth: 900, minHeight: 600)
        }
        .windowResizability(.contentSize)
        .defaultSize(width: 1100, height: 680)
        .defaultPosition(.trailing)
    }
}
