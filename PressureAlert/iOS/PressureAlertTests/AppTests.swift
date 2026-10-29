import PressureCore
import XCTest
@testable import PressureAlert

final class AppTests: XCTestCase {
    func testAlertRecordDecodesBackendJSON() throws {
        let json = """
        {"alerts":[{"id":3,"created_at":1790000000,"ts":1789999200,"direction":"fall","window_hours":3,
        "threshold_hpa":5.0,"change_hpa":-6.0,"pressure_hpa":1008.0,"status":"quiet_hours",
        "title":"Pressure falling fast","body":"Pressure is falling fast: down 6 hPa"}]}
        """
        struct Wrapper: Decodable { let alerts: [AlertRecord] }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .secondsSince1970
        let alert = try decoder.decode(Wrapper.self, from: Data(json.utf8)).alerts[0]
        XCTAssertEqual(alert.direction, .fall)
        XCTAssertEqual(alert.windowHours, 3)
        XCTAssertEqual(alert.time, Date(timeIntervalSince1970: 1_789_999_200))
        XCTAssertEqual(alert.statusDescription, "Not sent: quiet hours")
    }

    func testInstallUpdateEncodesSnakeCaseAndOmitsNils() throws {
        var body = BackendClient.InstallUpdate()
        body.apnsToken = "abcd"
        body.settings = AlertSettings()
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(body)) as? [String: Any])
        XCTAssertEqual(json["apns_token"] as? String, "abcd")
        XCTAssertNil(json["location"])
        let settings = try XCTUnwrap(json["settings"] as? [String: Any])
        XCTAssertNotNil(settings["quiet_hours"])
    }

    func testCacheKeyToleratesGPSWobble() {
        let a = SavedLocation(name: "A", latitude: 43.65321, longitude: -79.38321, timeZoneID: "America/Toronto")
        let b = SavedLocation(name: "A", latitude: 43.65399, longitude: -79.38001, timeZoneID: "America/Toronto")
        XCTAssertEqual(a.cacheKey, b.cacheKey)
    }

    func testLogEntryClampsSeverity() {
        XCTAssertEqual(LogEntry(severity: 14).severity, 10)
        XCTAssertEqual(LogEntry(severity: 0).severity, 1)
    }
}
