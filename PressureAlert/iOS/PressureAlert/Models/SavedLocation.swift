import Foundation

/// The one saved location (multi-location is v2). Exact coordinates stay on
/// the device; the backend snaps them to a ~10 km grid cell before storing.
struct SavedLocation: Codable, Hashable {
    var name: String
    var latitude: Double
    var longitude: Double
    var timeZoneID: String

    var timeZone: TimeZone { TimeZone(identifier: timeZoneID) ?? .current }

    /// Rounded key for the on-device cache, so a small GPS wobble does not
    /// throw away the cached series.
    var cacheKey: String { String(format: "%.2f,%.2f", latitude, longitude) }

    var calendar: Calendar {
        var calendar = Calendar.current
        calendar.timeZone = timeZone
        return calendar
    }
}
