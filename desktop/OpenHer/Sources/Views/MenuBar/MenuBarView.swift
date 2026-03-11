import SwiftUI

/// Menu bar dropdown — paper aesthetic, shows persona + quick actions.
struct MenuBarView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Connection status
            HStack(spacing: 6) {
                Circle()
                    .fill(appState.isConnected ? Paper.coral : Paper.faint)
                    .frame(width: 6, height: 6)
                Text(appState.isConnected ? "已连接" : "未连接")
                    .font(Paper.freqFont)
                    .foregroundStyle(Paper.herText)
            }

            Divider()

            // Current persona
            if let persona = appState.selectedPersona {
                HStack(spacing: 8) {
                    Circle()
                        .fill(Paper.ink.opacity(0.2))
                        .frame(width: 24, height: 24)
                        .overlay(
                            Text(String(persona.displayName.prefix(1)))
                                .font(.system(size: 12))
                                .foregroundStyle(Paper.ink)
                        )
                    VStack(alignment: .leading, spacing: 2) {
                        Text(persona.displayName)
                            .font(Paper.nameFont)
                            .foregroundStyle(Paper.herText)
                        Text("FREQ. 调频中 ∿")
                            .font(Paper.tinyFont)
                            .foregroundStyle(Paper.coral)
                    }
                }
            }

            Divider()

            // Persona list for switching
            if appState.personas.count > 1 {
                Text("切换角色")
                    .font(Paper.tinyFont)
                    .foregroundStyle(Paper.faint)

                ForEach(appState.personas) { persona in
                    Button {
                        appState.selectPersona(persona.personaId)
                    } label: {
                        Text(persona.displayName)
                            .font(Paper.freqFont)
                            .foregroundStyle(Paper.herText)
                    }
                    .buttonStyle(.plain)
                }

                Divider()
            }

            // Actions
            Button("打开对话 ⌘⇧O") {}
                .buttonStyle(.plain)
                .font(Paper.freqFont)

            Button("设置...") {
                NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
            }
            .buttonStyle(.plain)
            .font(Paper.freqFont)

            Button("退出") {
                NSApp.terminate(nil)
            }
            .buttonStyle(.plain)
            .font(Paper.freqFont)
            .foregroundStyle(Paper.coral)
        }
        .padding(16)
        .frame(width: 200)
    }
}
