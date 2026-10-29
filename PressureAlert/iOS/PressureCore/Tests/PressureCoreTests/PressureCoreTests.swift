import XCTest
@testable import PressureCore

private let t0 = Date(timeIntervalSince1970: 1_789_999_200) // on an hour boundary

private func series(_ values: [Double], start: Date = t0) -> PressureSeries {
    PressureSeries(values.enumerated().map { PressureSample(time: start.addingTimeInterval(Double($0.offset) * 3600), hPa: $0.element) })
}

private func hour(_ n: Int) -> Date { t0.addingTimeInterval(Double(n) * 3600) }

final class PressureSeriesTests: XCTestCase {
    func testChangeAndLookupFloorToTheHour() {
        let s = series([1010, 1009, 1008, 1004])
        XCTAssertEqual(s.change(at: hour(3), hours: 3), -6)
        XCTAssertEqual(s.change(at: hour(3).addingTimeInterval(1799), hours: 3), -6)
        XCTAssertNil(s.change(at: hour(2), hours: 3))
        XCTAssertEqual(s.current(at: hour(2).addingTimeInterval(600))?.hPa, 1008)
    }

    func testSamplesAreSortedAndDeduplicated() {
        let s = PressureSeries([
            PressureSample(time: hour(2), hPa: 1),
            PressureSample(time: hour(0), hPa: 2),
            PressureSample(time: hour(2), hPa: 3),
        ])
        XCTAssertEqual(s.samples.map(\.hPa), [2, 3])
    }
}

final class TrendTests: XCTestCase {
    func testLabels() {
        XCTAssertEqual(PressureTrend(change3h: -6).label, "Falling fast")
        XCTAssertEqual(PressureTrend(change3h: -5).label, "Falling fast")
        XCTAssertEqual(PressureTrend(change3h: -3.5).label, "Falling")
        XCTAssertEqual(PressureTrend(change3h: -1.2).label, "Falling slowly")
        XCTAssertEqual(PressureTrend(change3h: 0.4).label, "Steady")
        XCTAssertEqual(PressureTrend(change3h: 2).label, "Rising slowly")
        XCTAssertEqual(PressureTrend(change3h: 7).label, "Rising fast")
    }

    func testEveryTrendHasAnArrow() {
        for change in stride(from: -8.0, through: 8.0, by: 0.5) {
            XCTAssertTrue(PressureTrend(change3h: change).symbolName.hasPrefix("arrow."))
        }
    }
}

final class UnitTests: XCTestCase {
    func testFormatting() {
        XCTAssertEqual(PressureUnit.hPa.format(1008.4), "1008 hPa")
        XCTAssertEqual(PressureUnit.inHg.format(1020), "30.12 inHg")
        XCTAssertEqual(PressureUnit.mmHg.format(1020), "765 mmHg")
        XCTAssertEqual(PressureUnit.hPa.formatChange(-6), "6 hPa")
        XCTAssertEqual(PressureUnit.hPa.formatChange(5.26), "5.3 hPa")
        XCTAssertEqual(PressureUnit.hPa.formatSignedChange(-6), "\u{2212}6 hPa")
        XCTAssertEqual(PressureUnit.hPa.formatSignedChange(0.01), "0 hPa")
        XCTAssertEqual(PressureUnit.inHg.toHPa(PressureUnit.inHg.convert(1013.25)), 1013.25, accuracy: 1e-9)
    }
}

final class AlertSettingsTests: XCTestCase {
    func testJSONMatchesBackendShape() throws {
        let data = try JSONEncoder().encode(AlertSettings())
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["unit"] as? String, "hPa")
        XCTAssertNotNil(json["quiet_hours"])
        let fall = try XCTUnwrap((json["alerts"] as? [String: Any])?["fall"] as? [String: Any])
        let short = try XCTUnwrap(fall["short"] as? [String: Any])
        XCTAssertEqual(short["hpa"] as? Double, 5)
        XCTAssertEqual(short["hours"] as? Int, 3)
    }

    func testQuietHoursWrapMidnight() {
        let q = QuietHours(enabled: true, start: "22:00", end: "07:00")
        XCTAssertTrue(q.contains(minuteOfDay: 23 * 60))
        XCTAssertTrue(q.contains(minuteOfDay: 3 * 60))
        XCTAssertFalse(q.contains(minuteOfDay: 7 * 60))
        XCTAssertFalse(QuietHours(enabled: false).contains(minuteOfDay: 23 * 60))
        XCTAssertEqual(QuietHours.hhmm(minutes: 7 * 60 + 5), "07:05")
    }
}

final class AnalysisTests: XCTestCase {
    let rules = AlertRuleSet()

    func testCrossingBothDirections() {
        let fall = series([1013, 1011, 1010, 1008])
        XCTAssertEqual(PressureAnalysis.crossing(in: fall, at: hour(3), direction: .fall, rules: .default)?.change, -5)
        XCTAssertNil(PressureAnalysis.crossing(in: fall, at: hour(3), direction: .rise, rules: .default))
        let rise = series([1000, 1002, 1004, 1006])
        XCTAssertEqual(PressureAnalysis.crossing(in: rise, at: hour(3), direction: .rise, rules: .default)?.rule.hours, 3)
    }

    func testForecastSwingFindsFirstFutureCrossing() {
        // Steady through hour 6, then 6 hPa down by hour 9. Hour 8 is only
        // -4 over 3 hours, so hour 9 is the first crossing.
        let s = series([1012, 1012, 1012, 1012, 1012, 1012, 1012, 1010, 1008, 1006, 1006])
        let swing = PressureAnalysis.nextForecastSwing(in: s, after: hour(3), rules: rules)
        XCTAssertEqual(swing?.direction, .fall)
        XCTAssertEqual(swing?.time, hour(9))
        XCTAssertEqual(swing?.change, -6)
    }

    func testForecastSwingIgnoresCrossingAlreadyUnderway() {
        let s = series([1013, 1011, 1010, 1008, 1006, 1004])
        XCTAssertNil(PressureAnalysis.nextForecastSwing(in: s, after: hour(3), rules: rules))
    }

    func testDailySummariesFlagSwingDays() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let midnight = calendar.startOfDay(for: t0)
        // Day 1 steady, day 2 drops 12 hPa.
        var values = Array(repeating: 1015.0, count: 24)
        values += (0..<24).map { 1015 - Double($0) * 0.5 }
        let s = series(values, start: midnight)
        let days = PressureAnalysis.dailySummaries(in: s, calendar: calendar, from: midnight, days: 7, rules: rules)
        XCTAssertEqual(days.count, 2)
        XCTAssertFalse(days[0].isSwingDay)
        XCTAssertTrue(days[1].isSwingDay)
        XCTAssertEqual(days[1].high, 1015)
        XCTAssertEqual(days[1].low, 1003.5)
        XCTAssertEqual(days[1].netChange, -11.5)
    }

    func testAlertTextMatchesBackend() {
        let crossing = Crossing(direction: .fall, time: t0, pressure: 1008, change: -6, rule: AlertRule(enabled: true, hpa: 5, hours: 3))
        XCTAssertEqual(AlertText.title(for: crossing), "Pressure falling fast")
        XCTAssertEqual(
            AlertText.body(for: crossing, unit: .hPa),
            "Pressure is falling fast: down 6 hPa in the last 3 hours, now 1008 hPa. "
                + "Your alert is set for 5 hPa in 3 hours. A swing like this is often linked to headaches."
        )
    }
}

final class CSVExportTests: XCTestCase {
    func testPressureCSVHasAttributionAndChanges() {
        let csv = CSVExport.pressure(series([1010, 1009, 1008, 1004]), unit: .hPa, timeZone: TimeZone(identifier: "UTC")!)
        let lines = csv.split(separator: "\n").map(String.init)
        XCTAssertTrue(lines[0].contains("Open-Meteo"))
        XCTAssertEqual(lines[1], "time,pressure_msl_hPa,change_3h_hPa,change_24h_hPa")
        XCTAssertEqual(lines.count, 6)
        XCTAssertTrue(lines[5].hasSuffix(",1004.0,-6.0,"))
    }

    func testLogCSVEscapesNotesAndJoinsPressure() {
        let records = [LogRecord(date: hour(3).addingTimeInterval(900), severity: 7, note: "behind eyes, \"throbbing\"")]
        let csv = CSVExport.log(records, series: series([1010, 1009, 1008, 1004]), unit: .hPa, timeZone: TimeZone(identifier: "UTC")!)
        let row = csv.split(separator: "\n").map(String.init)[2]
        XCTAssertTrue(row.contains(",7,\"behind eyes, \"\"throbbing\"\"\",1004.0,-6.0,"))
    }
}
