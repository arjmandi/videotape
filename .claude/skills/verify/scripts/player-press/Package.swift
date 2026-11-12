// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "player-press",
    platforms: [.macOS(.v15)],
    dependencies: [.package(path: "../../../../../clients/macos/TapeKit")],
    targets: [
        .executableTarget(name: "player-press", dependencies: [.product(name: "TapeKit", package: "TapeKit")]),
    ]
)
