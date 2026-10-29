import Foundation

/// Plain-language trend from the 3-hour change, so a number in hPa always
/// comes with words (spec 4.1 item 2).
public enum PressureTrend: Sendable, Equatable {
    case fallingFast, falling, fallingSlowly, steady, risingSlowly, rising, risingFast

    /// |change| < 1 hPa/3 h is steady, < 3 slow, < 5 moderate, 5 or more fast.
    /// 5 hPa in 3 hours is also the default alert threshold.
    public init(change3h: Double) {
        let size = abs(change3h)
        let falling = change3h < 0
        switch size {
        case ..<1: self = .steady
        case ..<3: self = falling ? .fallingSlowly : .risingSlowly
        case ..<5: self = falling ? .falling : .rising
        default: self = falling ? .fallingFast : .risingFast
        }
    }

    public var label: String {
        switch self {
        case .fallingFast: return "Falling fast"
        case .falling: return "Falling"
        case .fallingSlowly: return "Falling slowly"
        case .steady: return "Steady"
        case .risingSlowly: return "Rising slowly"
        case .rising: return "Rising"
        case .risingFast: return "Rising fast"
        }
    }

    /// SF Symbol. Colour is never the only signal: views always show this
    /// arrow and `label` alongside any colour (spec 10).
    public var symbolName: String {
        switch self {
        case .fallingFast: return "arrow.down"
        case .falling, .fallingSlowly: return "arrow.down.right"
        case .steady: return "arrow.right"
        case .rising, .risingSlowly: return "arrow.up.right"
        case .risingFast: return "arrow.up"
        }
    }

    public var direction: PressureDirection? {
        switch self {
        case .fallingFast, .falling, .fallingSlowly: return .fall
        case .steady: return nil
        case .rising, .risingSlowly, .risingFast: return .rise
        }
    }
}

/// A threshold crossing at a given hour.
public struct Crossing: Hashable, Sendable {
    public let direction: PressureDirection
    public let time: Date
    public let pressure: Double
    public let change: Double
    public let rule: AlertRule

    public init(direction: PressureDirection, time: Date, pressure: Double, change: Double, rule: AlertRule) {
        self.direction = direction
        self.time = time
        self.pressure = pressure
        self.change = change
        self.rule = rule
    }

    /// How far past the threshold, as a ratio. 1.0 is exactly at it.
    public var severity: Double { abs(change) / max(rule.hpa, 0.1) }
}

public struct DaySummary: Identifiable, Sendable {
    public var id: Date { day }
    /// Start of the day in the location's time zone.
    public let day: Date
    public let samples: [PressureSample]
    public let high: Double
    public let low: Double
    /// Last hour minus first hour of the day.
    public let netChange: Double
    /// The strongest threshold crossing during the day, if any.
    public let swing: Crossing?

    public var isSwingDay: Bool { swing != nil }
    public var range: Double { high - low }
}

public enum PressureAnalysis {
    /// The first enabled rule (short window before long) crossed at `date`.
    /// Same rule as the backend's `find_crossing`.
    public static func crossing(
        in series: PressureSeries,
        at date: Date,
        direction: PressureDirection,
        rules: DirectionRules
    ) -> Crossing? {
        guard let pressure = series.value(at: date) else { return nil }
        for rule in rules.enabledRules {
            guard let delta = series.change(at: date, hours: rule.hours) else { continue }
            let moved = direction == .fall ? -delta : delta
            if moved >= rule.hpa {
                return Crossing(direction: direction, time: PressureSeries.floorHour(date), pressure: pressure, change: delta, rule: rule)
            }
        }
        return nil
    }

    public static func crossings(in series: PressureSeries, at date: Date, rules: AlertRuleSet) -> [Crossing] {
        PressureDirection.allCases.compactMap { crossing(in: series, at: date, direction: $0, rules: rules.rules(for: $0)) }
    }

    /// The home screen's "next swing" warning: the first forecast hour within
    /// `hours` after now where any enabled threshold would be crossed.
    /// A crossing that is already happening now does not count; the trend
    /// label and the push alert cover that.
    public static func nextForecastSwing(
        in series: PressureSeries,
        after now: Date,
        within hours: Int = 24,
        rules: AlertRuleSet
    ) -> Crossing? {
        let start = PressureSeries.floorHour(now)
        let ongoing = Set(crossings(in: series, at: start, rules: rules).map(\.direction))
        for offset in 1...max(hours, 1) {
            let time = start.addingTimeInterval(Double(offset) * PressureSeries.hour)
            let found = crossings(in: series, at: time, rules: rules).filter { !ongoing.contains($0.direction) }
            if let strongest = found.max(by: { $0.severity < $1.severity }) {
                return strongest
            }
        }
        return nil
    }

    /// One summary per calendar day (in `calendar`'s time zone) that has data,
    /// starting with the day containing `start`, for up to `days` days.
    public static func dailySummaries(
        in series: PressureSeries,
        calendar: Calendar,
        from start: Date,
        days: Int,
        rules: AlertRuleSet
    ) -> [DaySummary] {
        let firstDay = calendar.startOfDay(for: start)
        var result: [DaySummary] = []
        for index in 0..<days {
            guard let day = calendar.date(byAdding: .day, value: index, to: firstDay),
                  let next = calendar.date(byAdding: .day, value: 1, to: day) else { continue }
            let samples = series.samples.filter { $0.time >= day && $0.time < next }
            guard let first = samples.first, let last = samples.last else { continue }
            let values = samples.map(\.hPa)
            let swing = samples
                .flatMap { crossings(in: series, at: $0.time, rules: rules) }
                .max(by: { $0.severity < $1.severity })
            result.append(DaySummary(
                day: day,
                samples: samples,
                high: values.max()!,
                low: values.min()!,
                netChange: last.hPa - first.hPa,
                swing: swing
            ))
        }
        return result
    }
}

/// Plain-language wording, mirroring the backend's `alert_text` so the
/// in-app preview reads exactly like the push notification. Information-only
/// language: "often linked to", never a medical claim (spec 11).
public enum AlertText {
    static func isFast(_ rule: AlertRule) -> Bool { rule.hours <= 6 }

    static func hours(_ n: Int) -> String { n == 1 ? "1 hour" : "\(n) hours" }

    public static func title(for crossing: Crossing) -> String {
        let falling = crossing.direction == .fall
        if isFast(crossing.rule) {
            return falling ? "Pressure falling fast" : "Pressure rising fast"
        }
        return falling ? "Big pressure drop" : "Big pressure rise"
    }

    public static func body(for crossing: Crossing, unit: PressureUnit) -> String {
        let falling = crossing.direction == .fall
        let verb = falling ? "falling" : "rising"
        let lead = isFast(crossing.rule) ? "Pressure is \(verb) fast" : "Pressure is \(verb)"
        let window = crossing.rule.hours == 1 ? "hour" : "\(crossing.rule.hours) hours"
        return "\(lead): \(falling ? "down" : "up") \(unit.formatChange(crossing.change)) "
            + "in the last \(window), now \(unit.format(crossing.pressure)). "
            + "Your alert is set for \(unit.formatChange(crossing.rule.hpa)) in \(hours(crossing.rule.hours)). "
            + "A swing like this is often linked to headaches."
    }

    /// "may fall about 6 hPa over 3 hours", for the forecast swing card.
    public static func forecastPhrase(for crossing: Crossing, unit: PressureUnit) -> String {
        let verb = crossing.direction == .fall ? "fall" : "rise"
        return "may \(verb) about \(unit.formatChange(crossing.change)) over \(hours(crossing.rule.hours))"
    }
}
