import SwiftUI

/// Settings — paper aesthetic, server URL config.
struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @AppStorage("serverURL") private var serverURL = "http://localhost:8800"

    var body: some View {
        Form {
            Section("后端服务器") {
                TextField("URL", text: $serverURL)
                    .textFieldStyle(.roundedBorder)

                Button("保存并重连") {
                    appState.updateServerURL(serverURL)
                }
                .foregroundStyle(Paper.coral)
            }
        }
        .formStyle(.grouped)
        .frame(width: 360, height: 140)
    }
}
