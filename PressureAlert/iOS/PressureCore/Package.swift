// swift-tools-version:5.9
import PackageDescription

// Pure Foundation logic shared by the app: the pressure series, trend labels,
// daily pattern, forecast swing detection, units, alert wording, and CSV
// export. No UIKit/SwiftUI, so `swift test` runs it on macOS or Linux.
let package = Package(
    name: "PressureCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "PressureCore", targets: ["PressureCore"])
    ],
    targets: [
        .target(name: "PressureCore"),
        .testTarget(name: "PressureCoreTests", dependencies: ["PressureCore"])
    ]
)
