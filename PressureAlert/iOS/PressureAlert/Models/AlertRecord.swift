import Foundation
import PressureCore

/// One row of the backend's per-install alert history.
struct AlertRecord: Codable, Identifiable, Hashable {
    let id: Int
    let createdAt: Date
    /// The hour the crossing happened.
    let time: Date
    let direction: PressureDirection
    let windowHours: Int
    let thresholdHpa: Double
    let changeHpa: Double
    let pressureHpa: Double
    /// "sent", "quiet_hours", "no_token", "failed", "unregistered", "not_configured".
    let status: String
    let title: String
    let body: String

    enum CodingKeys: String, CodingKey {
        case id, createdAt, direction, windowHours, thresholdHpa, changeHpa, pressureHpa, status, title, body
        case time = "ts"
    }

    var statusDescription: String? {
        switch status {
        case "sent": return nil
        case "quiet_hours": return "Not sent: quiet hours"
        case "no_token", "unregistered": return "Not sent: notifications are off"
        case "not_configured": return "Not sent: push not set up on the server"
        default: return "Not delivered"
        }
    }
}
