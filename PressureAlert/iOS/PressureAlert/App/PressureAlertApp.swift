import SwiftData
import SwiftUI

@main
struct PressureAlertApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @Environment(\.scenePhase) private var scenePhase
    @State private var model = AppModel()
    let container: ModelContainer

    init() {
        do {
            container = try ModelContainer(for: LogEntry.self)
        } catch {
            fatalError("Failed to create SwiftData ModelContainer: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .onAppear { appDelegate.attach(model) }
                .onOpenURL { model.handle(url: $0) }
        }
        .modelContainer(container)
        .onChange(of: scenePhase) { _, phase in
            guard phase == .active, model.hasCompletedOnboarding else { return }
            Task {
                await model.refreshNotificationStatus()
                await model.syncNow()
                await model.refresh()
            }
        }
    }
}
