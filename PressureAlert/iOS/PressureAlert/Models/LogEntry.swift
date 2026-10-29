import Foundation
import SwiftData
import PressureCore

/// One headache or pain log entry. Stored on the device only; never sent to
/// the backend. No diagnosis, no treatment suggestions (spec 4.1 item 7).
@Model
final class LogEntry {
    var id: UUID
    var date: Date
    /// 1 to 10.
    var severity: Int
    var note: String

    init(date: Date = .now, severity: Int, note: String = "") {
        self.id = UUID()
        self.date = date
        self.severity = min(max(severity, 1), 10)
        self.note = note
    }

    var record: LogRecord { LogRecord(date: date, severity: severity, note: note) }
}
