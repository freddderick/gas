import Foundation
import Observation
import PressureCore
import UIKit
import UserNotifications

/// App-wide state: the saved location, alert settings, the cached series,
/// and the connection to the backend.
@MainActor
@Observable
final class AppModel {
    static let detailURL = URL(string: "pressurealert://pressure")!

    enum Tab: Hashable { case now, pattern, log, settings }

    enum Status: Equatable {
        case idle
        case loading
        case ok
        /// Backend is fetching this location for the first time.
        case pending
        /// "Forecast unavailable, alerts paused" (spec 6.2).
        case unavailable(String)
        /// Could not reach the server; showing cached data.
        case offline
    }

    // MARK: Persisted state

    var hasCompletedOnboarding: Bool {
        didSet { defaults.set(hasCompletedOnboarding, forKey: Keys.onboarding) }
    }

    var settings: AlertSettings {
        didSet {
            guard settings != oldValue else { return }
            persist(settings, Keys.settings)
            scheduleSync()
        }
    }

    private(set) var location: SavedLocation?

    // MARK: Feed

    private(set) var series = PressureSeries([])
    private(set) var fetchedAt: Date?
    private(set) var status: Status = .idle
    private(set) var alertHistory: [AlertRecord] = []
    private(set) var lastSyncError: String?

    // MARK: Notifications and navigation

    private(set) var notificationStatus: UNAuthorizationStatus = .notDetermined
    private(set) var pushToken: String?
    var selectedTab: Tab = .now
    var showPressureDetail = false

    // MARK: Dependencies

    /// Nil in prototype mode (no backend URL configured).
    let backend: BackendClient?
    var isPrototypeMode: Bool { backend == nil }
    private let direct = OpenMeteoDirectClient()
    private let defaults: UserDefaults
    @ObservationIgnored private var syncTask: Task<Void, Never>?
    @ObservationIgnored private var pendingRetries = 0

    private enum Keys {
        static let onboarding = "hasCompletedOnboarding"
        static let settings = "alertSettings"
        static let location = "savedLocation"
    }

    init(defaults: UserDefaults = .standard, bundle: Bundle = .main) {
        self.defaults = defaults
        hasCompletedOnboarding = defaults.bool(forKey: Keys.onboarding)
        settings = Self.restore(AlertSettings.self, Keys.settings, defaults) ?? AlertSettings()
        location = Self.restore(SavedLocation.self, Keys.location, defaults)

        let configured = (bundle.object(forInfoDictionaryKey: "PABackendURL") as? String)?
            .trimmingCharacters(in: .whitespaces) ?? ""
        if let url = URL(string: configured), url.scheme == "https" || url.scheme == "http" {
            backend = BackendClient(baseURL: url, identity: .loadOrCreate())
        } else {
            backend = nil
        }

        if let cached = DiskCache.load(), cached.locationKey == location?.cacheKey {
            series = PressureSeries(cached.samples)
            fetchedAt = cached.fetchedAt
            alertHistory = cached.alerts
            status = cached.status == .unavailable ? .unavailable(cached.message ?? Self.unavailableText) : .idle
        }
    }

    static let unavailableText = "Forecast unavailable, alerts paused"

    // MARK: Derived values for the UI

    var unit: PressureUnit { settings.unit }
    var calendar: Calendar { location?.calendar ?? .current }

    var current: PressureSample? { series.current(at: .now) }

    var trend: PressureTrend? {
        guard let current, let change = series.change(at: current.time, hours: 3) else { return nil }
        return PressureTrend(change3h: change)
    }

    var nextSwing: Crossing? {
        PressureAnalysis.nextForecastSwing(in: series, after: .now, within: 24, rules: settings.alerts)
    }

    func days(_ count: Int = 7) -> [DaySummary] {
        PressureAnalysis.dailySummaries(in: series, calendar: calendar, from: .now, days: count, rules: settings.alerts)
    }

    /// True when the data on screen should not be trusted for decisions.
    var alertsPaused: Bool {
        if case .unavailable = status { return true }
        return false
    }

    // MARK: Actions

    func setLocation(_ newLocation: SavedLocation) async {
        let moved = newLocation.cacheKey != location?.cacheKey
        location = newLocation
        persist(newLocation, Keys.location)
        if moved {
            series = PressureSeries([])
            alertHistory = []
            fetchedAt = nil
            DiskCache.clear()
        }
        await syncNow()
        await refresh()
    }

    func refresh() async {
        guard let location else { return }
        if status != .ok { status = .loading }
        do {
            let result: FeedResult
            if let backend {
                result = try await backend.pressure()
                alertHistory = (try? await backend.alerts()) ?? alertHistory
            } else {
                result = try await direct.fetch(latitude: location.latitude, longitude: location.longitude)
            }
            apply(result, for: location)
        } catch FeedError.http(let code) where code == 404 || code == 409 {
            // The server lost or never received this install; re-register.
            await syncNow()
            status = series.isEmpty ? .pending : .offline
        } catch {
            status = series.isEmpty ? .unavailable("Can't reach the forecast right now. Pull to try again.") : .offline
        }
    }

    private func apply(_ result: FeedResult, for location: SavedLocation) {
        if !result.samples.isEmpty || result.status == .ok {
            series = PressureSeries(result.samples)
        }
        fetchedAt = result.fetchedAt ?? fetchedAt
        switch result.status {
        case .ok: status = .ok
        case .pending: status = .pending
        case .unavailable: status = .unavailable(result.message ?? Self.unavailableText)
        }
        DiskCache.save(CachedFeed(
            locationKey: location.cacheKey,
            samples: series.samples,
            status: result.status,
            message: result.message,
            fetchedAt: fetchedAt,
            alerts: alertHistory
        ))
        // A new location's first fetch happens in the background on the
        // server; check back shortly.
        pendingRetries = result.status == .pending ? pendingRetries + 1 : 0
        if result.status == .pending, pendingRetries <= 5 {
            Task {
                try? await Task.sleep(for: .seconds(4))
                await self.refresh()
            }
        }
    }

    // MARK: Notifications

    func refreshNotificationStatus() async {
        notificationStatus = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
        if notificationStatus == .authorized || notificationStatus == .provisional {
            UIApplication.shared.registerForRemoteNotifications()
        }
    }

    /// Asked from onboarding with an explanation first, never cold on launch
    /// (spec 11).
    @discardableResult
    func requestNotifications() async -> Bool {
        let granted = (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        await refreshNotificationStatus()
        return granted
    }

    func updatePushToken(_ token: String) {
        guard token != pushToken else { return }
        pushToken = token
        scheduleSync()
    }

    // MARK: Backend sync

    private func scheduleSync() {
        syncTask?.cancel()
        syncTask = Task {
            try? await Task.sleep(for: .milliseconds(800))
            guard !Task.isCancelled else { return }
            await syncNow()
        }
    }

    /// Sends token, location, time zone and settings. Idempotent.
    func syncNow() async {
        guard let backend, let location else { return }
        var body = BackendClient.InstallUpdate()
        body.apnsToken = pushToken
        #if DEBUG
        body.apnsEnvironment = "sandbox"
        #else
        body.apnsEnvironment = "production"
        #endif
        body.location = .init(latitude: location.latitude, longitude: location.longitude, name: location.name)
        body.timezone = location.timeZoneID
        body.settings = settings
        do {
            try await backend.update(body)
            lastSyncError = nil
        } catch {
            lastSyncError = "Couldn't save your alert settings to the server. They'll be sent next time the app opens."
        }
    }

    /// "Delete my data": removes the server record, local cache and settings.
    func deleteServerData() async throws {
        try await backend?.deleteInstall()
        InstallIdentity.reset()
        DiskCache.clear()
        alertHistory = []
    }

    // MARK: Deep links

    func handle(url: URL) {
        guard url.scheme == Self.detailURL.scheme else { return }
        selectedTab = .now
        showPressureDetail = true
        Task { await refresh() }
    }

    // MARK: Persistence helpers

    private func persist<T: Encodable>(_ value: T, _ key: String) {
        defaults.set(try? JSONEncoder().encode(value), forKey: key)
    }

    private static func restore<T: Decodable>(_ type: T.Type, _ key: String, _ defaults: UserDefaults) -> T? {
        guard let data = defaults.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }
}
