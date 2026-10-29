import CoreMotion
import PressureCore
import SwiftUI

/// Where an alert's deep link lands: the current reading, the recent changes
/// that alerts are computed from, and the 72-hour chart.
struct PressureDetailView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        List {
            if let banner = model.banner {
                Section {
                    StatusBanner(banner: banner)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                }
            }
            if let current = model.current {
                Section("Now") {
                    LabeledContent("Sea-level pressure", value: model.unit.format(current.hPa))
                    if let trend = model.trend {
                        LabeledContent("Trend") { TrendLabel(trend: trend, font: .body) }
                    }
                    LabeledContent("Reading for", value: current.time.shortDayHour(in: model.calendar.timeZone))
                }
                Section {
                    ForEach([3, 6, 24], id: \.self) { hours in
                        LabeledContent("Last \(hours) hours") {
                            if let change = model.series.change(at: current.time, hours: hours) {
                                ChangeLabel(change: change, unit: model.unit)
                            } else {
                                Text("Not enough data").foregroundStyle(.secondary)
                            }
                        }
                    }
                } header: {
                    Text("Recent change")
                } footer: {
                    Text("Alerts compare the pressure now with the pressure 3 hours and 24 hours ago (or the windows you set).")
                }
            }
            Section("Next 72 hours") {
                PressureChart(
                    samples: model.series.samples(from: .now.addingTimeInterval(-24 * 3600), through: .now.addingTimeInterval(72 * 3600)),
                    unit: model.unit,
                    timeZone: model.calendar.timeZone,
                    now: .now,
                    height: 260
                )
                .padding(.vertical, 8)
            }
            if let swing = model.nextSwing {
                Section("Swing ahead") {
                    ForecastSwingCard(swing: swing)
                        .listRowInsets(EdgeInsets())
                }
            }
            if CMAltimeter.isRelativeAltitudeAvailable() {
                Section {
                    NavigationLink("Phone sensor (station pressure)") { BarometerView() }
                } footer: {
                    Text("A live reading from your phone's barometer. It measures pressure where the phone is, so it reads lower at altitude and changes in lifts, cars and planes. It is never used for alerts.")
                }
            }
            Section {
                NavigationLink("What do these numbers mean?") { ExplainerView() }
            } footer: {
                Text(Copy.attribution)
            }
        }
        .navigationTitle("Pressure detail")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refresh() }
    }
}

struct AlertHistoryView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        List {
            if model.isPrototypeMode {
                Text("Alert history comes from the alert server, which isn't connected in prototype mode.")
                    .foregroundStyle(.secondary)
            } else if model.alertHistory.isEmpty {
                ContentUnavailableView(
                    "No alerts yet",
                    systemImage: "bell",
                    description: Text("When pressure crosses one of your thresholds, the alert shows up here.")
                )
            }
            ForEach(model.alertHistory) { alert in
                AlertRow(alert: alert)
            }
        }
        .navigationTitle("Alert history")
        .refreshable { await model.refresh() }
    }
}

private struct AlertRow: View {
    @Environment(AppModel.self) private var model
    let alert: AlertRecord

    var body: some View {
        let unit = model.unit
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Label(
                    alert.direction == .fall ? "Fall" : "Rise",
                    systemImage: alert.direction == .fall ? "arrow.down" : "arrow.up"
                )
                .font(.headline)
                .foregroundStyle(Color.forDirection(alert.direction))
                Spacer()
                Text(alert.time.formatted(date: .abbreviated, time: .shortened))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Text("\(alert.direction == .fall ? "Down" : "Up") \(unit.formatChange(alert.changeHpa)) in \(alert.windowHours) h, to \(unit.format(alert.pressureHpa))")
            Text("Threshold: \(unit.formatChange(alert.thresholdHpa)) in \(alert.windowHours) h")
                .font(.caption)
                .foregroundStyle(.secondary)
            if let note = alert.statusDescription {
                Text(note).font(.caption).foregroundStyle(.orange)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// Spec 4.1 item 6: what sea-level pressure is, what counts as a fast swing,
/// and that pressure is one trigger among many, not a diagnosis.
struct ExplainerView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                section(
                    "What is barometric pressure?",
                    "It's the weight of the air above you. Weather systems push it up and down. High pressure usually brings settled weather; low pressure often brings cloud, wind and rain."
                )
                section(
                    "Why \"sea-level\" pressure?",
                    "Pressure is lower the higher up you are, so this app uses pressure adjusted to sea level. That way \"down 5 hPa\" means the same thing in Calgary as in Toronto, and the number doesn't jump when you take a lift or drive up a hill."
                )
                section(
                    "What's a normal reading?",
                    "Most days sit between about 1000 and 1025 hPa (29.5 to 30.3 inHg). Below about 1000 hPa is a deep low; above about 1025 hPa is a strong high. The number itself matters less than how fast it changes."
                )
                section(
                    "What counts as a fast swing?",
                    "A change of 1 hPa or less over 3 hours is steady. 3 hPa or more over 3 hours is a noticeable change, and 5 hPa or more is fast. Over a day, 10 hPa or more is a big swing. Alerts default to 5 hPa in 3 hours and 10 hPa in 24 hours, in either direction, and you can change both."
                )
                section(
                    "How the trend words work",
                    "Steady: under 1 hPa in 3 hours. Slowly: 1 to 3. Falling or Rising: 3 to 5. Fast: 5 or more."
                )
                section(
                    "Pressure is one trigger among many",
                    "Some people notice headaches or joint pain when pressure swings, either down or up. Sleep, stress, food, hormones and many other things matter too. This app can help you see whether pressure lines up with how you feel, but it can't tell you why you feel the way you do."
                )
                Text(Copy.disclaimer)
                    .font(.callout)
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
                Text(Copy.attributionDetail)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .padding()
        }
        .navigationTitle("About pressure")
    }

    private func section(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.headline)
            Text(body)
        }
    }
}
