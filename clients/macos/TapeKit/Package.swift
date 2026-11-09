// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "TapeKit",
    platforms: [.macOS(.v15)],
    products: [
        .library(name: "TapeKit", targets: ["TapeKit"]),
    ],
    targets: [
        .target(name: "TapeKit"),
        .testTarget(name: "TapeKitTests", dependencies: ["TapeKit"], resources: [.copy("Fixtures")]),
    ]
)
