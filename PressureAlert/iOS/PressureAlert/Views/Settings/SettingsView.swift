import CoreMotion
import PressureCore
import SwiftUI
import UserNotifications

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openURL) private var openURL
    @State private var confirmingDelete = false
    @State private var deleteError: String?

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            Form {
                Section("Location") {
                    NavigationLink {
                        LocationPickerView()
                    } label: {
                        LabeledContent("Location", value: model.location?.name ?? "Not set")
                    }
                }

                Section {
                    NavigationLink("Alert thresholds") { AlertSettingsView() }
                    Toggle("Quiet hours", isOn: $model.settings.quietHours.enabled)
                    if model.settings.quietHours.enabled {
                        DatePicker("From", selection: quietBinding(\.start), displayedComponents: .hourAndMinute)
                        DatePicker("Until", selection: quietBinding(\.end), displayedComponents: .hourAndMinute)
                    }
                    notificationRow
                    NavigationLink("Alert history") { AlertHistoryView() }
                } header: {
                    Text("Alerts")
                } footer: {
                    Text(model.settings.quietHours.enabled
                         ? "No alerts during quiet hours, in \(model.location?.name ?? "your location")'s local time. Turn quiet hours off to get alerts overnight."
                         : "Alerts can arrive at any time, including overnight.")
                }
                if let error = model.lastSyncError {
                    Section { Label(error, systemImage: "exclamationmark.icloud").foregroundStyle(.orange) }
                }

                Section("Units") {
                    Picker("Pressure unit", selection: $model.settings.unit) {
                        ForEach(PressureUnit.allCases) { unit in
                            Text(unit.displayName).tag(unit)
                        }
                    }
                }

                Section("Your data") {
                    NavigationLink("Export pressure and log") { ExportView() }
                    if !model.isPrototypeMode {
                        Button("Delete my data from the alert server", role: .destructive) { confirmingDelete = true }
                    }
                }

                if CMAltimeter.isRelativeAltitudeAvailable() {
                    Section {
                        NavigationLink("Phone barometer") { BarometerView() }
                    } footer: {
                        Text("Station pressure from your phone's sensor. For interest only; never used for alerts.")
                    }
                }

                Section("About") {
                    NavigationLink("What do these numbers mean?") { ExplainerView() }
                    NavigationLink("Privacy") { PrivacyView() }
                    Text(Copy.disclaimer)
                        .font(.footnote)
                    Link(destination: Copy.attributionURL) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(Copy.attribution)
                            Text(Copy.attributionDetail).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if model.isPrototypeMode {
                        Label("Prototype mode: no alert server configured. The app reads Open-Meteo's free endpoint, which is for non-commercial use only.", systemImage: "hammer")
                            .font(.footnote)
                    }
                    LabeledContent("Version", value: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "")
                }
            }
            .navigationTitle("Settings")
            .confirmationDialog(
                "Delete your alert settings, push token and alert history from the server?",
                isPresented: $confirmingDelete,
                titleVisibility: .visible
            ) {
                Button("Delete", role: .destructive) {
                    Task {
                        do {
                            try await model.deleteServerData()
                        } catch {
                            deleteError = "Couldn't reach the server. Try again when you're online."
                        }
                    }
                }
            } message: {
                Text("Alerts stop until you open the app again. Your log stays on this phone.")
            }
            .alert("Not deleted", isPresented: Binding(get: { deleteError != nil }, set: { if !$0 { deleteError = nil } })) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(deleteError ?? "")
            }
        }
    }

    @ViewBuilder
    private var notificationRow: some View {
        switch model.notificationStatus {
        case .authorized, .provisional, .ephemeral:
            LabeledContent("Notifications", value: model.pushToken == nil && !model.isPrototypeMode ? "Allowed, connecting…" : "On")
        case .denied:
            Button("Notifications are off. Open Settings") {
                if let url = URL(string: UIApplication.openNotificationSettingsURLString) { openURL(url) }
            }
        default:
            Button("Turn on notifications") { Task { await model.requestNotifications() } }
        }
    }

    /// Bridges "HH:mm" strings to the DatePicker's Date, in the location's
    /// time zone so quiet hours mean local time there.
    private func quietBinding(_ keyPath: WritableKeyPath<QuietHours, String>) -> Binding<Date> {
        let calendar = model.calendar
        return Binding(
            get: {
                let minutes = QuietHours.minutes(model.settings.quietHours[keyPath: keyPath]) ?? 0
                return calendar.date(bySettingHour: minutes / 60, minute: minutes % 60, second: 0, of: .now) ?? .now
            },
            set: { date in
                let parts = calendar.dateComponents([.hour, .minute], from: date)
                model.settings.quietHours[keyPath: keyPath] = QuietHours.hhmm(minutes: (parts.hour ?? 0) * 60 + (parts.minute ?? 0))
            }
        )
    }
}

struct PrivacyView: View {
    var body: some View {
        List {
            Section {
                Text("No account, no sign-in, no email.")
                Text("Your location is used only to fetch the pressure forecast for that place. The alert server stores it rounded to an area about 10 km across, never your exact position.")
                Text("The server keeps a random install ID, your push notification token, your alert settings and your alert history, only so it can send alerts. Nothing is sold or shared.")
                Text("Your headache and pain log stays on this phone. It leaves only if you export it.")
                Text("No ads, no tracking, no analytics that identify you.")
                Text("\"Delete my data from the alert server\" in Settings removes everything the server holds about this install.")
            }
        }
        .navigationTitle("Privacy")
    }
}
