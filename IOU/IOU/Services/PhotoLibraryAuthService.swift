import Photos
import SwiftUI

/// Thin wrapper around `PHPhotoLibrary` authorization so views can observe
/// permission state without talking to the Photos framework directly.
@Observable
final class PhotoLibraryAuthService {
    private(set) var status: PHAuthorizationStatus

    init() {
        status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
    }

    func refresh() {
        status = PHPhotoLibrary.authorizationStatus(for: .readWrite)
    }

    @discardableResult
    func requestAccess() async -> PHAuthorizationStatus {
        let newStatus = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        await MainActor.run { self.status = newStatus }
        return newStatus
    }

    var isAuthorized: Bool {
        status == .authorized || status == .limited
    }

    var isDenied: Bool {
        status == .denied || status == .restricted
    }
}
