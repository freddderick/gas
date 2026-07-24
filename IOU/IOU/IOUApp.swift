import SwiftUI
import SwiftData

@main
struct IOUApp: App {
    let container: ModelContainer

    init() {
        do {
            container = try ModelContainer(for: Receipt.self)
        } catch {
            fatalError("Failed to create SwiftData ModelContainer: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
        }
        .modelContainer(container)
    }
}
