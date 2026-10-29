import PressureCore
import SwiftUI

/// Spec 10, top to bottom: current pressure and trend, the next 72 hours,
/// any forecast swing in the next 24 hours, today's log button, and a link
/// to the pattern view.
struct HomeView: View {
    @Environment(AppModel.self) private var model
    @State private var showingLogSheet = false

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let banner = model.banner { StatusBanner(banner: banner) }
                    CurrentPressureCard()
                    chartCard
                    if let swing = model.nextSwing {
                        ForecastSwingCard(swing: swing)
                    }
                    Button {
                        showingLogSheet = true
                    } label: {
                        Label("Log a headache or pain", systemImage: "plus.circle.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)

                    VStack(spacing: 0) {
                        navRow("See the 7-day pattern", icon: "calendar") { model.selectedTab = .pattern }
                        Divider()
                        NavigationLink { AlertHistoryView() } label: {
                            rowLabel("Alert history", icon: "bell.badge")
                        }
                        Divider()
                        NavigationLink { ExplainerView() } label: {
                            rowLabel("What do these numbers mean?", icon: "questionmark.circle")
                        }
                    }
                    .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))

                    Text(Copy.attribution)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle(model.location?.name ?? "Pressure")
            .refreshable { await model.refresh() }
            .navigationDestination(isPresented: $model.showPressureDetail) {
                PressureDetailView()
            }
            .sheet(isPresented: $showingLogSheet) {
                LogEntrySheet()
            }
        }
    }

    private var chartCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Next 72 hours").font(.headline)
                Spacer()
                NavigationLink("Details") { PressureDetailView() }
                    .font(.subheadline)
            }
            let now = Date.now
            let samples = model.series.samples(
                from: now.addingTimeInterval(-12 * 3600),
                through: now.addingTimeInterval(72 * 3600)
            )
            if samples.isEmpty {
                ContentUnavailableView("No forecast yet", systemImage: "chart.xyaxis.line", description: Text("Pull down to refresh."))
                    .frame(height: 220)
            } else {
                PressureChart(samples: samples, unit: model.unit, timeZone: model.calendar.timeZone, now: now)
            }
        }
        .padding()
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }

    private func navRow(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { rowLabel(title, icon: icon) }
    }

    private func rowLabel(_ title: String, icon: String) -> some View {
        HStack {
            Label(title, systemImage: icon)
            Spacer()
            Image(systemName: "chevron.right").foregroundStyle(.tertiary)
        }
        .padding()
        .contentShape(Rectangle())
    }
}

struct CurrentPressureCard: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Sea-level pressure")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            if let current = model.current {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(model.unit.formatValue(current.hPa))
                        .font(.system(size: 64, weight: .semibold, design: .rounded))
                        .minimumScaleFactor(0.5)
                        .lineLimit(1)
                    Text(model.unit.rawValue)
                        .font(.title2)
                        .foregroundStyle(.secondary)
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("\(model.unit.formatValue(current.hPa)) \(model.unit.spokenName)")

                if let trend = model.trend {
                    TrendLabel(trend: trend, font: .title3.weight(.semibold))
                }
                if let change = model.series.change(at: current.time, hours: 3) {
                    Text(changeSentence(change))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                if let fetchedAt = model.fetchedAt {
                    Text("Forecast updated \(fetchedAt.formatted(.relative(presentation: .named)))")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            } else if model.status == .loading || model.status == .pending {
                ProgressView().frame(maxWidth: .infinity, minHeight: 100)
            } else {
                Text("No reading yet").font(.title2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16))
    }

    private func changeSentence(_ change: Double) -> String {
        if abs(change) < 0.5 { return "About the same as 3 hours ago." }
        return "\(change < 0 ? "Down" : "Up") \(model.unit.formatChange(change)) in the last 3 hours."
    }
}

struct ForecastSwingCard: View {
    @Environment(AppModel.self) private var model
    let swing: Crossing

    var body: some View {
        let tz = model.calendar.timeZone
        VStack(alignment: .leading, spacing: 6) {
            Label(
                swing.direction == .fall ? "Swing ahead: falling" : "Swing ahead: rising",
                systemImage: swing.direction == .fall ? "arrow.down.forward.circle.fill" : "arrow.up.forward.circle.fill"
            )
            .font(.headline)
            .foregroundStyle(Color.forDirection(swing.direction))
            Text("The forecast says pressure \(AlertText.forecastPhrase(for: swing, unit: model.unit)), reaching about \(model.unit.format(swing.pressure)) around \(swing.time.shortDayHour(in: tz)).")
                .font(.subheadline)
            Text("Forecasts change. You'll get an alert if it happens.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color.forDirection(swing.direction).opacity(0.12), in: RoundedRectangle(cornerRadius: 16))
        .accessibilityElement(children: .combine)
    }
}
