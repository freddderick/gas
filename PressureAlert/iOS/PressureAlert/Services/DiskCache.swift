import Foundation
import PressureCore

/// The last good series and alert history, so the app reads offline
/// (spec 3.3 item 2).
struct CachedFeed: Codable {
    var locationKey: String
    var samples: [PressureSample]
    var status: FeedResult.Status
    var message: String?
    var fetchedAt: Date?
    var alerts: [AlertRecord]
}

enum DiskCache {
    private static var url: URL {
        let directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory.appendingPathComponent("feed-cache.json")
    }

    static func load() -> CachedFeed? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(CachedFeed.self, from: data)
    }

    static func save(_ feed: CachedFeed) {
        guard let data = try? JSONEncoder().encode(feed) else { return }
        try? data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }

    static func clear() {
        try? FileManager.default.removeItem(at: url)
    }
}
