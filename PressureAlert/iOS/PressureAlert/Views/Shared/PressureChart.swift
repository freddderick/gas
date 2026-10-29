import Charts
import PressureCore
import SwiftUI

/// Sea-level pressure line chart (Swift Charts). Only ever plots
/// `PressureSeries` samples, which are pressure_msl by construction.
struct PressureChart: View {
    let samples: [PressureSample]
    let unit: PressureUnit
    let timeZone: TimeZone
    /// Draws a "Now" rule and dims the past.
    var now: Date?
    var height: CGFloat = 220

    private var yDomain: ClosedRange<Double> {
        let values = samples.map { unit.convert($0.hPa) }
        guard let low = values.min(), let high = values.max() else { return 0...1 }
        // At least ~8 hPa of vertical range so a steady day looks steady.
        let minimumSpan = unit.convert(8)
        let mid = (low + high) / 2
        let half = max((high - low) / 2, minimumSpan / 2) * 1.1
        return (mid - half)...(mid + half)
    }

    var body: some View {
        Chart {
            ForEach(samples, id: \.time) { sample in
                LineMark(
                    x: .value("Time", sample.time),
                    y: .value("Pressure", unit.convert(sample.hPa))
                )
                .interpolationMethod(.monotone)
                .foregroundStyle(by: .value("Period", (now.map { sample.time <= $0 } ?? false) ? "Past" : "Forecast"))
            }
            if let now {
                RuleMark(x: .value("Now", now))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                    .foregroundStyle(.secondary)
                    .annotation(position: .top, alignment: .leading) {
                        Text("Now").font(.caption2).foregroundStyle(.secondary)
                    }
            }
        }
        .chartForegroundStyleScale(["Past": Color.secondary.opacity(0.6), "Forecast": Color.accentColor])
        .chartLegend(.hidden)
        .chartYScale(domain: yDomain)
        .chartYAxisLabel(unit.rawValue)
        .chartXAxis {
            AxisMarks(values: .stride(by: .hour, count: samples.count > 48 ? 24 : 6)) { value in
                AxisGridLine()
                AxisValueLabel {
                    if let date = value.as(Date.self) {
                        Text(axisLabel(date))
                    }
                }
            }
        }
        .frame(height: height)
        .accessibilityChartDescriptor(self)
    }

    private func axisLabel(_ date: Date) -> String {
        var style = samples.count > 48 ? Date.FormatStyle().weekday(.abbreviated) : Date.FormatStyle().hour()
        style.timeZone = timeZone
        return date.formatted(style)
    }
}

/// VoiceOver audio graph and a spoken summary for the chart (spec 10).
extension PressureChart: AXChartDescriptorRepresentable {
    func makeChartDescriptor() -> AXChartDescriptor {
        let values = samples.map { unit.convert($0.hPa) }
        let start = samples.first?.time ?? .now
        let end = samples.last?.time ?? .now
        let xAxis = AXNumericDataAxisDescriptor(
            title: "Time",
            range: 0...max(end.timeIntervalSince(start) / 3600, 1),
            gridlinePositions: []
        ) { hours in
            start.addingTimeInterval(hours * 3600).shortDayHour(in: timeZone)
        }
        let yAxis = AXNumericDataAxisDescriptor(
            title: "Sea-level pressure in \(unit.spokenName)",
            range: (values.min() ?? 0)...(values.max() ?? 1),
            gridlinePositions: []
        ) { value in
            "\(String(format: unit == .inHg ? "%.2f" : "%.0f", value)) \(unit.spokenName)"
        }
        let series = AXDataSeriesDescriptor(
            name: "Pressure",
            isContinuous: true,
            dataPoints: samples.map {
                AXDataPoint(x: $0.time.timeIntervalSince(start) / 3600, y: unit.convert($0.hPa))
            }
        )
        let summary: String
        if let low = samples.min(by: { $0.hPa < $1.hPa }), let high = samples.max(by: { $0.hPa < $1.hPa }) {
            summary = "Lowest \(unit.format(low.hPa)) around \(low.time.shortDayHour(in: timeZone)). "
                + "Highest \(unit.format(high.hPa)) around \(high.time.shortDayHour(in: timeZone))."
        } else {
            summary = "No data."
        }
        return AXChartDescriptor(
            title: "Sea-level pressure",
            summary: summary,
            xAxis: xAxis,
            yAxis: yAxis,
            additionalAxes: [],
            series: [series]
        )
    }
}
