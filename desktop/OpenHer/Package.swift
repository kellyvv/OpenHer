// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "OpenHer",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "OpenHer",
            path: "Sources",
            resources: [
                .copy("Resources/chat_bg.png")
            ]
        ),
    ]
)
