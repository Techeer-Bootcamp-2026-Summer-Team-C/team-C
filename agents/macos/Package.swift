// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "EDRMacAgent",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "EDRAgentCore", targets: ["EDRAgentCore"]),
        .executable(name: "edr-macos-agent", targets: ["EDRMacAgent"]),
    ],
    targets: [
        .target(
            name: "EDRAgentCore",
            linkerSettings: [.linkedLibrary("sqlite3"), .linkedFramework("CoreServices")]
        ),
        .executableTarget(name: "EDRMacAgent", dependencies: ["EDRAgentCore"]),
        .testTarget(name: "EDRAgentCoreTests", dependencies: ["EDRAgentCore"]),
    ]
)
