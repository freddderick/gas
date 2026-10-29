import PressureCore
import SwiftUI
import UIKit

/// Data for the one-page PDF summary.
struct ClinicianReport {
    let series: PressureSeries
    let records: [LogRecord]
    let unit: PressureUnit
    let location: SavedLocation?

    var timeZone: TimeZone { location?.timeZone ?? .current }

    /// The last 14 days of log entries, newest first, capped to fit a page.
    var recentRecords: [LogRecord] {
        let cutoff = Date.now.addingTimeInterval(-14 * 86400)
        return Array(records.filter { $0.date >= cutoff }.sorted { $0.date > $1.date }.prefix(18))
    }

    /// Past 14 days of the series, for the chart.
    var pastSamples: [PressureSample] {
        series.samples(from: .now.addingTimeInterval(-14 * 86400), through: .now)
    }
}

enum ReportRenderer {
    /// US Letter in points.
    static let pageSize = CGSize(width: 612, height: 792)

    @MainActor
    static func render(to url: URL, report: ClinicianReport) throws {
        let renderer = ImageRenderer(content: ReportPage(report: report).frame(width: pageSize.width, height: pageSize.height))
        renderer.proposedSize = ProposedViewSize(pageSize)
        var failure: Error?
        renderer.render { size, draw in
            var box = CGRect(origin: .zero, size: pageSize)
            guard let consumer = CGDataConsumer(url: url as CFURL),
                  let context = CGContext(consumer: consumer, mediaBox: &box, nil) else {
                failure = CocoaError(.fileWriteUnknown)
                return
            }
            context.beginPDFPage(nil)
            draw(context)
            context.endPDFPage()
            context.closePDF()
        }
        if let failure { throw failure }
    }
}

private struct ReportPage: View {
    let report: ClinicianReport

    var body: some View {
        let unit = report.unit
        let tz = report.timeZone
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Pressure and symptom summary").font(.system(size: 20, weight: .bold))
                Text("\(report.location?.name ?? "Unknown location") · prepared \(Date.now.formatted(date: .long, time: .omitted))")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }

            Text("Sea-level pressure, past 14 days (\(unit.rawValue))").font(.system(size: 12, weight: .semibold))
            if report.pastSamples.isEmpty {
                Text("No pressure history available.").font(.system(size: 11))
            } else {
                PressureChart(samples: report.pastSamples, unit: unit, timeZone: tz, height: 170)
            }

            Text("Log entries, past 14 days").font(.system(size: 12, weight: .semibold))
            if report.recentRecords.isEmpty {
                Text("No entries.").font(.system(size: 11))
            } else {
                Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 3) {
                    GridRow {
                        Text("When"); Text("Severity"); Text("Pressure"); Text("3 h change"); Text("Note")
                    }
                    .font(.system(size: 10, weight: .semibold))
                    Divider()
                    ForEach(Array(report.recentRecords.enumerated()), id: \.offset) { _, record in
                        GridRow {
                            Text(dateText(record.date, tz))
                            Text("\(record.severity)/10")
                            Text(report.series.value(at: record.date).map { unit.format($0) } ?? "–")
                            Text(report.series.change(at: record.date, hours: 3).map { unit.formatSignedChange($0) } ?? "–")
                            Text(record.note).lineLimit(1)
                        }
                        .font(.system(size: 10))
                    }
                }
            }

            Spacer(minLength: 0)
            Text("Pressure is one possible trigger among many. This summary shows timing only and does not show cause.")
                .font(.system(size: 9))
            Text(Copy.disclaimer).font(.system(size: 9))
            Text(Copy.attributionDetail).font(.system(size: 9)).foregroundStyle(.secondary)
        }
        .padding(40)
        .frame(width: ReportRenderer.pageSize.width, height: ReportRenderer.pageSize.height, alignment: .topLeading)
        .background(Color.white)
        .environment(\.colorScheme, .light)
    }

    private func dateText(_ date: Date, _ tz: TimeZone) -> String {
        var style = Date.FormatStyle().month(.abbreviated).day().hour().minute()
        style.timeZone = tz
        return date.formatted(style)
    }
}
