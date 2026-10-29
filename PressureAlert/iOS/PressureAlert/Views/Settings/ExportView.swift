import PressureCore
import SwiftData
import SwiftUI

/// CSV of the pressure series, CSV of the log, and a one-page PDF summary
/// for a clinician visit (spec 4.1 item 8). Every file carries the
/// Open-Meteo attribution.
struct ExportView: View {
    @Environment(AppModel.self) private var model
    @Query(sort: \LogEntry.date) private var entries: [LogEntry]
    @State private var files: ExportFiles?
    @State private var error: String?

    var body: some View {
        List {
            if let files {
                Section {
                    ShareLink(item: files.pressureCSV) {
                        Label("Pressure series (CSV)", systemImage: "chart.xyaxis.line")
                    }
                    ShareLink(item: files.logCSV) {
                        Label("Headache and pain log (CSV)", systemImage: "list.bullet.clipboard")
                    }
                    ShareLink(item: files.summaryPDF) {
                        Label("Summary for a clinician (PDF)", systemImage: "doc.richtext")
                    }
                } footer: {
                    Text("The log export includes the pressure and the 3- and 24-hour change at each entry, so you can line them up in a spreadsheet. Files include the note: \(Copy.attribution).")
                }
            } else if let error {
                Text(error).foregroundStyle(.orange)
            } else {
                ProgressView()
            }
            Section {
                Text("Exports cover the pressure history and forecast stored for \(model.location?.name ?? "your location") (up to 14 days of history from the alert server) and your full log.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Export")
        .task(id: entries.count) { build() }
    }

    private func build() {
        do {
            files = try ExportFiles.write(
                series: model.series,
                records: entries.map(\.record),
                unit: model.unit,
                location: model.location
            )
        } catch {
            self.error = "Couldn't create the export files."
        }
    }
}

struct ExportFiles {
    let pressureCSV: URL
    let logCSV: URL
    let summaryPDF: URL

    @MainActor
    static func write(series: PressureSeries, records: [LogRecord], unit: PressureUnit, location: SavedLocation?) throws -> ExportFiles {
        let tz = location?.timeZone ?? .current
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("export", isDirectory: true)
        try? FileManager.default.removeItem(at: directory)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let stamp = Date.now.formatted(.iso8601.year().month().day())

        let pressure = directory.appendingPathComponent("pressure-\(stamp).csv")
        try CSVExport.pressure(series, unit: unit, timeZone: tz).write(to: pressure, atomically: true, encoding: .utf8)

        let log = directory.appendingPathComponent("pain-log-\(stamp).csv")
        try CSVExport.log(records, series: series, unit: unit, timeZone: tz).write(to: log, atomically: true, encoding: .utf8)

        let pdf = directory.appendingPathComponent("pressure-summary-\(stamp).pdf")
        try ReportRenderer.render(
            to: pdf,
            report: ClinicianReport(series: series, records: records, unit: unit, location: location)
        )
        return ExportFiles(pressureCSV: pressure, logCSV: log, summaryPDF: pdf)
    }
}
