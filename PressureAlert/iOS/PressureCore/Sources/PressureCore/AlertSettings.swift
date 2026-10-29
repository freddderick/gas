import Foundation

public enum PressureDirection: String, Codable, CaseIterable, Sendable {
    case fall
    case rise

    public var word: String { self == .fall ? "Falling" : "Rising" }
}

/// "Alert when pressure moves `hPa` within `hours`."
public struct AlertRule: Codable, Hashable, Sendable {
    public var enabled: Bool
    public var hpa: Double
    public var hours: Int

    public init(enabled: Bool, hpa: Double, hours: Int) {
        self.enabled = enabled
        self.hpa = hpa
        self.hours = hours
    }
}

/// A short-window rule (default 5 hPa in 3 h) and a long-window rule
/// (default 10 hPa in 24 h) for one direction.
public struct DirectionRules: Codable, Hashable, Sendable {
    public var short: AlertRule
    public var long: AlertRule

    public init(short: AlertRule, long: AlertRule) {
        self.short = short
        self.long = long
    }

    public static let `default` = DirectionRules(
        short: AlertRule(enabled: true, hpa: 5, hours: 3),
        long: AlertRule(enabled: true, hpa: 10, hours: 24)
    )

    public var enabledRules: [AlertRule] { [short, long].filter(\.enabled) }
}

public struct AlertRuleSet: Codable, Hashable, Sendable {
    public var fall: DirectionRules
    public var rise: DirectionRules

    public init(fall: DirectionRules = .default, rise: DirectionRules = .default) {
        self.fall = fall
        self.rise = rise
    }

    public func rules(for direction: PressureDirection) -> DirectionRules {
        direction == .fall ? fall : rise
    }
}

public struct QuietHours: Codable, Hashable, Sendable {
    public var enabled: Bool
    /// "HH:mm", 24-hour, in the location's time zone.
    public var start: String
    public var end: String

    public init(enabled: Bool = true, start: String = "22:00", end: String = "07:00") {
        self.enabled = enabled
        self.start = start
        self.end = end
    }

    public static func minutes(_ hhmm: String) -> Int? {
        let parts = hhmm.split(separator: ":").compactMap { Int($0) }
        guard parts.count == 2, (0..<24).contains(parts[0]), (0..<60).contains(parts[1]) else { return nil }
        return parts[0] * 60 + parts[1]
    }

    public static func hhmm(minutes: Int) -> String {
        String(format: "%02d:%02d", (minutes / 60) % 24, minutes % 60)
    }

    /// Mirrors the backend: wraps past midnight when start > end.
    public func contains(minuteOfDay minute: Int) -> Bool {
        guard enabled, let s = Self.minutes(start), let e = Self.minutes(end), s != e else { return false }
        return s < e ? (minute >= s && minute < e) : (minute >= s || minute < e)
    }
}

/// Everything the backend needs to decide on alerts. The JSON shape matches
/// the backend's `SettingsBody` exactly.
public struct AlertSettings: Codable, Hashable, Sendable {
    public var unit: PressureUnit
    public var alerts: AlertRuleSet
    public var quietHours: QuietHours

    public init(unit: PressureUnit = .hPa, alerts: AlertRuleSet = AlertRuleSet(), quietHours: QuietHours = QuietHours()) {
        self.unit = unit
        self.alerts = alerts
        self.quietHours = quietHours
    }

    enum CodingKeys: String, CodingKey {
        case unit
        case alerts
        case quietHours = "quiet_hours"
    }
}
