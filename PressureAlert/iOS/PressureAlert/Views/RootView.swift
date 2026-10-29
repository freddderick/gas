import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if model.hasCompletedOnboarding && model.location != nil {
            MainTabView()
        } else {
            OnboardingView()
        }
    }
}

struct MainTabView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        TabView(selection: $model.selectedTab) {
            HomeView()
                .tabItem { Label("Now", systemImage: "gauge.with.dots.needle.33percent") }
                .tag(AppModel.Tab.now)
            PatternView()
                .tabItem { Label("7 Days", systemImage: "calendar") }
                .tag(AppModel.Tab.pattern)
            LogView()
                .tabItem { Label("Log", systemImage: "list.bullet.clipboard") }
                .tag(AppModel.Tab.log)
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
                .tag(AppModel.Tab.settings)
        }
        .task {
            await model.refreshNotificationStatus()
            await model.syncNow()
            await model.refresh()
        }
    }
}
