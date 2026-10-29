import PressureCore
import SwiftUI
import UserNotifications

/// Wording used in more than one place, so it stays identical everywhere it
/// is required (spec 11).
enum Copy {
    static let disclaimer = "This app provides weather information only. It is not a medical device and does not diagnose, treat, cure, or prevent any disease. If you have frequent or severe headaches, talk to a clinician."
    static let attribution = "Pressure data: Open-Meteo"
    static let attributionDetail = "Weather data by Open-Meteo.com, licensed under CC BY 4.0."
    static let attributionURL = URL(string: "https://open-meteo.com/")!
}

extension Color {
    static let fall = Color("FallColor")
    static let rise = Color("RiseColor")

    static func forDirection(_ direction: PressureDirection?) -> Color {
        switch direction {
        case .fall: return .fall
        case .rise: return .rise
        case nil: return .secondary
        }
    }
}

/// Arrow + words + colour. Colour is never the only signal (spec 10).
struct TrendLabel: View {
    let trend: PressureTrend
    var font: Font = .headline

    var body: some View {
        Label(trend.label, systemImage: trend.symbolName)
            .font(font)
            .foregroundStyle(Color.forDirection(trend.direction))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Trend: \(trend.label)")
    }
}

/// "Down 6 hPa" with an arrow, for changes in lists.
struct ChangeLabel: View {
    let change: Double
    let unit: PressureUnit

    private var direction: PressureDirection? {
        abs(change) < 0.5 ? nil : (change < 0 ? .fall : .rise)
    }

    private var words: String {
        switch direction {
        case .fall: return "Down \(unit.formatChange(change))"
        case .rise: return "Up \(unit.formatChange(change))"
        case nil: return "Little change"
        }
    }

    var body: some View {
        Label(words, systemImage: direction == .fall ? "arrow.down.right" : direction == .rise ? "arrow.up.right" : "arrow.right")
            .foregroundStyle(Color.forDirection(direction))
    }
}

struct Banner: Equatable {
    let icon: String
    let text: String
}

extension AppModel {
    /// Anything that makes the numbers on screen less trustworthy, or stops
    /// alerts reaching the person.
    var banner: Banner? {
        switch status {
        case .unavailable(let message):
            return Banner(icon: "exclamationmark.triangle", text: message)
        case .offline:
            let age = fetchedAt.map { " from \($0.formatted(.relative(presentation: .named)))" } ?? ""
            return Banner(icon: "wifi.slash", text: "Offline. Showing saved data\(age).")
        case .pending:
            return Banner(icon: "hourglass", text: "Getting the forecast for your location…")
        default:
            break
        }
        if isPrototypeMode {
            return Banner(icon: "hammer", text: "Prototype mode: reading Open-Meteo directly. Push alerts need the backend.")
        }
        if notificationStatus == .denied {
            return Banner(icon: "bell.slash", text: "Notifications are off, so alerts can't reach you. Turn them on in Settings.")
        }
        return nil
    }
}

struct StatusBanner: View {
    let banner: Banner

    var body: some View {
        Label(banner.text, systemImage: banner.icon)
            .font(.subheadline)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(.yellow.opacity(0.18), in: RoundedRectangle(cornerRadius: 12))
            .accessibilityElement(children: .combine)
    }
}

extension Date {
    /// "Thu 3 PM" in the given time zone.
    func shortDayHour(in timeZone: TimeZone) -> String {
        var style = Date.FormatStyle().weekday(.abbreviated).hour()
        style.timeZone = timeZone
        return formatted(style)
    }

    func dayTitle(in timeZone: TimeZone) -> String {
        var style = Date.FormatStyle().weekday(.wide).month(.abbreviated).day()
        style.timeZone = timeZone
        return formatted(style)
    }
}
