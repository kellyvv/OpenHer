import SwiftUI

/// Settings — paper aesthetic, server URL config.
struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @AppStorage("serverURL") private var serverURL = "http://localhost:8800"

    var body: some View {
        Form {
            Section(L10n.str("后端服务器", en: "Backend Server")) {
                TextField("URL", text: $serverURL)
                    .textFieldStyle(.roundedBorder)

                Button(L10n.str("保存并重连", en: "Save & Reconnect")) {
                    appState.updateServerURL(serverURL)
                }
                .foregroundStyle(Paper.coral)
            }

            Section(L10n.str("展示", en: "Display")) {
                Toggle(L10n.str("仅显示已就绪角色", en: "Show ready personas only"), isOn: $appState.showOnlyReadyPersonas)
                    .help(L10n.str("开启后，仅展示有待唤醒展柜图片的角色", en: "When enabled, only personas with a cabinet image are shown"))
            }
        }
        .formStyle(.grouped)
        .frame(width: 360, height: 200)
    }
}
