import Foundation

/// A headache or pain log entry, decoupled from SwiftData so export is testable.
public struct LogRecord: Sendable, Hashable {
    public let date: Date
    public let severity: Int
    public let note: String

    public init(date: Date, severity: Int, note: String) {
        self.date = date
        self.severity = severity
        self.note = note
    }
}

public enum CSVExport {
    /// Required by Open-Meteo's CC BY 4.0 licence on every export (spec 5.1).
    public static let attribution = "Pressure data: Open-Meteo (open-meteo.com), CC BY 4.0"
    public static let disclaimer = "Weather information only, not medical advice."

    static func headerComment(_ what: String) -> String {
        "# \(what). Sea-level pressure (pressure_msl). \(attribution). \(disclaimer)"
    }

    static func timestamp(_ date: Date, _ timeZone: TimeZone) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.timeZone = timeZone
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.string(from: date)
    }

    static func number(_ hPa: Double?, _ unit: PressureUnit, decimals: Int) -> String {
        guard let hPa else { return "" }
        return String(format: "%.\(decimals)f", unit.convert(hPa))
    }

    /// RFC 4180: quote fields containing commas, quotes or line breaks.
    public static func escape(_ field: String) -> String {
        guard field.contains(where: { $0 == "," || $0 == "\"" || $0 == "\n" || $0 == "\r" }) else { return field }
        return "\"" + field.replacingOccurrences(of: "\"", with: "\"\"") + "\""
    }

    static func decimals(_ unit: PressureUnit) -> Int { unit == .inHg ? 3 : 1 }

    public static func pressure(_ series: PressureSeries, unit: PressureUnit, timeZone: TimeZone) -> String {
        let u = unit.rawValue
        var lines = [
            headerComment("Hourly pressure"),
            "time,pressure_msl_\(u),change_3h_\(u),change_24h_\(u)",
        ]
        let d = decimals(unit)
        for sample in series.samples {
            lines.append([
                timestamp(sample.time, timeZone),
                number(sample.hPa, unit, decimals: d),
                number(series.change(at: sample.time, hours: 3), unit, decimals: d),
                number(series.change(at: sample.time, hours: 24), unit, decimals: d),
            ].joined(separator: ","))
        }
        return lines.joined(separator: "\n") + "\n"
    }

    /// The log, with the pressure and recent change at each entry's hour, so
    /// it can be overlaid against the pressure series in a spreadsheet.
    public static func log(_ records: [LogRecord], series: PressureSeries, unit: PressureUnit, timeZone: TimeZone) -> String {
        let u = unit.rawValue
        var lines = [
            headerComment("Headache and pain log"),
            "time,severity_1_to_10,note,pressure_msl_\(u),change_3h_\(u),change_24h_\(u)",
        ]
        let d = decimals(unit)
        for record in records.sorted(by: { $0.date < $1.date }) {
            lines.append([
                timestamp(record.date, timeZone),
                String(record.severity),
                escape(record.note),
                number(series.value(at: record.date), unit, decimals: d),
                number(series.change(at: record.date, hours: 3), unit, decimals: d),
                number(series.change(at: record.date, hours: 24), unit, decimals: d),
            ].joined(separator: ","))
        }
        return lines.joined(separator: "\n") + "\n"
    }
}
