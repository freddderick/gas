import PressureCore
import SwiftUI

/// Spec 10: one row per day with high, low and net change, swing days
/// highlighted, and a tap through to that day's hourly chart.
struct PatternView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        NavigationStack {
            List {
                if let banner = model.banner {
                    Section {
                        StatusBanner(banner: banner)
                            .listRowInsets(EdgeInsets())
                            .listRowBackground(Color.clear)
                    }
                }
                let days = model.days(7)
                if days.isEmpty {
                    ContentUnavailableView("No forecast yet", systemImage: "calendar", description: Text("Pull down to refresh."))
                }
                Section {
                    ForEach(days) { day in
                        NavigationLink {
                            DayDetailView(day: day)
                        } label: {
                            DayRow(day: day)
                        }
                        .listRowBackground(day.isSwingDay ? Color.forDirection(day.swing?.direction).opacity(0.12) : nil)
                    }
                } footer: {
                    Text("Swing days are days when the forecast crosses one of your alert thresholds. \(Copy.attribution).")
                }
            }
            .navigationTitle("7-day pattern")
            .refreshable { await model.refresh() }
        }
    }
}

private struct DayRow: View {
    @Environment(AppModel.self) private var model
    let day: DaySummary

    var body: some View {
        let unit = model.unit
        let tz = model.calendar.timeZone
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(day.day.dayTitle(in: tz)).font(.headline)
                Spacer()
                if let swing = day.swing {
                    Label("Swing day", systemImage: swing.direction == .fall ? "arrow.down.circle.fill" : "arrow.up.circle.fill")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Color.forDirection(swing.direction))
                }
            }
            HStack(spacing: 16) {
                Text("High \(unit.formatValue(day.high))")
                Text("Low \(unit.formatValue(day.low))")
                Spacer()
                ChangeLabel(change: day.netChange, unit: unit)
            }
            .font(.subheadline)
            if let swing = day.swing {
                Text("\(swing.direction == .fall ? "Falls" : "Rises") \(unit.formatChange(swing.change)) in \(swing.rule.hours) h, around \(swing.time.shortDayHour(in: tz))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}

struct DayDetailView: View {
    @Environment(AppModel.self) private var model
    let day: DaySummary

    var body: some View {
        let unit = model.unit
        let tz = model.calendar.timeZone
        List {
            Section {
                PressureChart(samples: day.samples, unit: unit, timeZone: tz, now: isToday ? .now : nil, height: 260)
                    .padding(.vertical, 8)
            }
            Section("Summary") {
                LabeledContent("High", value: unit.format(day.high))
                LabeledContent("Low", value: unit.format(day.low))
                LabeledContent("Range", value: unit.formatChange(day.range))
                LabeledContent("Start to end") { ChangeLabel(change: day.netChange, unit: unit) }
                if let swing = day.swing {
                    LabeledContent("Biggest swing") {
                        Text("\(swing.direction == .fall ? "Down" : "Up") \(unit.formatChange(swing.change)) in \(swing.rule.hours) h")
                            .foregroundStyle(Color.forDirection(swing.direction))
                    }
                }
            }
            Section("Hourly") {
                ForEach(day.samples, id: \.time) { sample in
                    LabeledContent {
                        Text(unit.format(sample.hPa)).monospacedDigit()
                    } label: {
                        Text(hourLabel(sample.time, tz))
                    }
                }
            }
        }
        .navigationTitle(day.day.dayTitle(in: tz))
        .navigationBarTitleDisplayMode(.inline)
    }

    private var isToday: Bool {
        model.calendar.isDate(day.day, inSameDayAs: .now)
    }

    private func hourLabel(_ date: Date, _ tz: TimeZone) -> String {
        var style = Date.FormatStyle().hour().minute()
        style.timeZone = tz
        return date.formatted(style)
    }
}
