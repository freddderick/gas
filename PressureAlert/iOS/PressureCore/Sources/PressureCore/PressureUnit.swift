import Foundation

public enum PressureUnit: String, Codable, CaseIterable, Identifiable, Sendable {
    case hPa
    case inHg
    case mmHg

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .hPa: return "Hectopascals (hPa)"
        case .inHg: return "Inches of mercury (inHg)"
        case .mmHg: return "Millimetres of mercury (mmHg)"
        }
    }

    /// Words for VoiceOver, which reads "hPa" badly.
    public var spokenName: String {
        switch self {
        case .hPa: return "hectopascals"
        case .inHg: return "inches of mercury"
        case .mmHg: return "millimetres of mercury"
        }
    }

    public var perHPa: Double {
        switch self {
        case .hPa: return 1
        case .inHg: return 0.029529983071445
        case .mmHg: return 0.750061683
        }
    }

    var pressureDecimals: Int { self == .inHg ? 2 : 0 }
    var changeDecimals: Int { self == .inHg ? 2 : 1 }

    public func convert(_ hPa: Double) -> Double { hPa * perHPa }
    public func toHPa(_ value: Double) -> Double { value / perHPa }

    /// "1008" (no unit).
    public func formatValue(_ hPa: Double) -> String {
        String(format: "%.\(pressureDecimals)f", convert(hPa))
    }

    /// "1008 hPa".
    public func format(_ hPa: Double) -> String {
        "\(formatValue(hPa)) \(rawValue)"
    }

    /// Magnitude only, trailing zeros trimmed: "6 hPa", "5.3 hPa", "0.18 inHg".
    public func formatChange(_ hPa: Double) -> String {
        "\(Self.trim(String(format: "%.\(changeDecimals)f", abs(convert(hPa))))) \(rawValue)"
    }

    /// "+6 hPa" / "−6 hPa" / "0 hPa".
    public func formatSignedChange(_ hPa: Double) -> String {
        let magnitude = formatChange(hPa)
        if magnitude.hasPrefix("0 ") { return magnitude }
        return (hPa < 0 ? "\u{2212}" : "+") + magnitude
    }

    static func trim(_ text: String) -> String {
        guard text.contains(".") else { return text }
        var trimmed = text
        while trimmed.hasSuffix("0") { trimmed.removeLast() }
        if trimmed.hasSuffix(".") { trimmed.removeLast() }
        return trimmed
    }
}
