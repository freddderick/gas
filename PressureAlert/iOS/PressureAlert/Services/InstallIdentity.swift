import Foundation
import Security

/// The anonymous identity this install uses with the backend: a random UUID
/// plus a random secret, kept in the Keychain. No account, no email, nothing
/// tied to the person (spec 4.1 item 11).
struct InstallIdentity: Codable, Equatable {
    let id: UUID
    let secret: String

    private static let service = "ca.andywood.PressureAlert.install"
    private static let account = "identity"

    static func loadOrCreate() -> InstallIdentity {
        if let existing = load() { return existing }
        let identity = InstallIdentity(id: UUID(), secret: randomSecret())
        save(identity)
        return identity
    }

    /// Forget this identity, e.g. after "Delete my data". The next launch
    /// gets a fresh, unrelated one.
    static func reset() {
        SecItemDelete(baseQuery as CFDictionary)
    }

    private static var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    private static func load() -> InstallIdentity? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return try? JSONDecoder().decode(InstallIdentity.self, from: data)
    }

    private static func save(_ identity: InstallIdentity) {
        guard let data = try? JSONEncoder().encode(identity) else { return }
        SecItemDelete(baseQuery as CFDictionary)
        var item = baseQuery
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(item as CFDictionary, nil)
    }

    private static func randomSecret() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        if SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) != errSecSuccess {
            bytes = (0..<32).map { _ in UInt8.random(in: 0...255) }
        }
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}
