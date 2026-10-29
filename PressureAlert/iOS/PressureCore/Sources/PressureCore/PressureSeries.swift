import Foundation

/// One hourly sea-level pressure value (Open-Meteo `pressure_msl`), in hPa.
public struct PressureSample: Codable, Hashable, Sendable {
    public let time: Date
    public let hPa: Double

    public init(time: Date, hPa: Double) {
        self.time = time
        self.hPa = hPa
    }
}

/// An hourly sea-level pressure series from a single provider.
///
/// By design this type only ever holds `pressure_msl`. Surface pressure and
/// phone-sensor readings are never put in a `PressureSeries` (spec 5.3).
public struct PressureSeries: Sendable {
    public static let hour: TimeInterval = 3600

    /// Sorted oldest first, one sample per hour.
    public let samples: [PressureSample]
    private let byHour: [Int: Double]

    public init(_ samples: [PressureSample]) {
        var byHour: [Int: Double] = [:]
        for sample in samples {
            byHour[Self.hourKey(sample.time)] = sample.hPa
        }
        self.byHour = byHour
        self.samples = byHour.keys.sorted().map { key in
            PressureSample(time: Date(timeIntervalSince1970: TimeInterval(key) * Self.hour), hPa: byHour[key]!)
        }
    }

    public static func hourKey(_ date: Date) -> Int {
        Int((date.timeIntervalSince1970 / hour).rounded(.down))
    }

    public static func floorHour(_ date: Date) -> Date {
        Date(timeIntervalSince1970: TimeInterval(hourKey(date)) * hour)
    }

    public var isEmpty: Bool { samples.isEmpty }
    public var first: PressureSample? { samples.first }
    public var last: PressureSample? { samples.last }

    /// The value for the hour containing `date`.
    public func value(at date: Date) -> Double? {
        byHour[Self.hourKey(date)]
    }

    /// pressure(at) - pressure(at - hours). Negative means falling.
    public func change(at date: Date, hours: Int) -> Double? {
        guard let now = value(at: date),
              let then = value(at: date.addingTimeInterval(-Double(hours) * Self.hour)) else {
            return nil
        }
        return now - then
    }

    /// The latest sample at or before `now`: the "current" reading.
    public func current(at now: Date) -> PressureSample? {
        samples.last { $0.time <= now }
    }

    public func samples(from start: Date, through end: Date) -> [PressureSample] {
        samples.filter { $0.time >= start && $0.time <= end }
    }
}
