import Foundation
import PressureCore

/// The latest series plus what the source said about it.
struct FeedResult {
    enum Status: String, Codable {
        case ok
        /// The backend has not fetched this location yet.
        case pending
        /// The provider is down or the series is stale. Alerts are paused.
        case unavailable
    }

    var samples: [PressureSample]
    var status: Status
    var message: String?
    var fetchedAt: Date?
}

enum FeedError: LocalizedError {
    case http(Int)
    case badResponse

    var errorDescription: String? {
        switch self {
        case .http(let code): return "The server returned an error (\(code))."
        case .badResponse: return "The server sent something unexpected."
        }
    }
}

// MARK: - Backend

/// Talks to the developer-owned backend (spec 6). The backend polls
/// Open-Meteo, evaluates thresholds and sends push alerts, so they fire with
/// the app closed.
struct BackendClient {
    let baseURL: URL
    let identity: InstallIdentity
    var session: URLSession = .shared

    struct LocationBody: Encodable {
        let latitude: Double
        let longitude: Double
        let name: String
    }

    struct InstallUpdate: Encodable {
        var apnsToken: String?
        var apnsEnvironment: String?
        var location: LocationBody?
        var timezone: String?
        var settings: AlertSettings?
    }

    private struct PressureResponse: Decodable {
        struct Point: Decodable {
            let t: Int
            let msl: Double
        }
        let status: FeedResult.Status
        let message: String?
        let fetchedAt: Int?
        let hourly: [Point]
    }

    private struct AlertsResponse: Decodable {
        let alerts: [AlertRecord]
    }

    private var installURL: URL {
        baseURL.appendingPathComponent("v1/installs/\(identity.id.uuidString.lowercased())")
    }

    private func request(_ url: URL, method: String = "GET", body: Data? = nil) -> URLRequest {
        var request = URLRequest(url: url, timeoutInterval: 20)
        request.httpMethod = method
        request.setValue("Bearer \(identity.secret)", forHTTPHeaderField: "Authorization")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }

    private func send(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw FeedError.badResponse }
        guard (200..<300).contains(http.statusCode) else { throw FeedError.http(http.statusCode) }
        return data
    }

    private static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .secondsSince1970
        return decoder
    }

    func update(_ body: InstallUpdate) async throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        _ = try await send(request(installURL, method: "PUT", body: try encoder.encode(body)))
    }

    func pressure() async throws -> FeedResult {
        let data = try await send(request(installURL.appendingPathComponent("pressure")))
        let response = try Self.decoder.decode(PressureResponse.self, from: data)
        return FeedResult(
            samples: response.hourly.map { PressureSample(time: Date(timeIntervalSince1970: TimeInterval($0.t)), hPa: $0.msl) },
            status: response.status,
            message: response.message,
            fetchedAt: response.fetchedAt.map { Date(timeIntervalSince1970: TimeInterval($0)) }
        )
    }

    func alerts() async throws -> [AlertRecord] {
        var components = URLComponents(url: installURL.appendingPathComponent("alerts"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "limit", value: "200")]
        let data = try await send(request(components.url!))
        return try Self.decoder.decode(AlertsResponse.self, from: data).alerts
    }

    func deleteInstall() async throws {
        _ = try await send(request(installURL, method: "DELETE"))
    }
}

// MARK: - Prototype mode

/// Used only when no backend URL is configured: reads Open-Meteo's free,
/// non-commercial endpoint directly so the app can be tried in the simulator.
/// Push alerts need the backend, so they are off in this mode. Never ship an
/// App Store build in this mode (spec 5.1).
struct OpenMeteoDirectClient {
    var session: URLSession = .shared

    private struct Response: Decodable {
        struct Hourly: Decodable {
            let time: [Int]
            let pressureMsl: [Double?]
        }
        let hourly: Hourly
    }

    func fetch(latitude: Double, longitude: Double) async throws -> FeedResult {
        var components = URLComponents(string: "https://api.open-meteo.com/v1/forecast")!
        components.queryItems = [
            URLQueryItem(name: "latitude", value: String(format: "%.4f", latitude)),
            URLQueryItem(name: "longitude", value: String(format: "%.4f", longitude)),
            // pressure_msl only: the one-variable rule (spec 5.3).
            URLQueryItem(name: "hourly", value: "pressure_msl"),
            URLQueryItem(name: "past_days", value: "2"),
            URLQueryItem(name: "forecast_days", value: "7"),
            URLQueryItem(name: "timezone", value: "GMT"),
            URLQueryItem(name: "timeformat", value: "unixtime"),
        ]
        let (data, response) = try await session.data(from: components.url!)
        guard let http = response as? HTTPURLResponse else { throw FeedError.badResponse }
        guard http.statusCode == 200 else { throw FeedError.http(http.statusCode) }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let hourly = try decoder.decode(Response.self, from: data).hourly
        let samples = zip(hourly.time, hourly.pressureMsl).compactMap { time, value in
            value.map { PressureSample(time: Date(timeIntervalSince1970: TimeInterval(time)), hPa: $0) }
        }
        return FeedResult(samples: samples, status: samples.isEmpty ? .unavailable : .ok, message: nil, fetchedAt: .now)
    }
}
