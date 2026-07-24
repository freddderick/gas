import SwiftUI
import Photos

/// Loads and displays the `PHAsset` behind a `Receipt`'s `assetIdentifier`.
/// Falls back to a placeholder if the original photo has been deleted from Photos.
struct AsyncPhotoImage: View {
    let assetIdentifier: String
    var targetSize: CGSize = CGSize(width: 300, height: 300)
    var contentMode: ContentMode = .fill

    @State private var image: UIImage?
    @State private var didFail = false

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: contentMode)
            } else if didFail {
                ZStack {
                    Rectangle().fill(Color.secondary.opacity(0.15))
                    Image(systemName: "photo.badge.exclamationmark")
                        .foregroundStyle(.secondary)
                }
            } else {
                ZStack {
                    Rectangle().fill(Color.secondary.opacity(0.1))
                    ProgressView()
                }
            }
        }
        .task(id: assetIdentifier) {
            image = nil
            didFail = false
            guard let asset = PhotoImageLoader.shared.fetchAsset(for: assetIdentifier) else {
                didFail = true
                return
            }
            let loaded = await PhotoImageLoader.shared.thumbnail(for: asset, targetSize: targetSize)
            if let loaded {
                image = loaded
            } else {
                didFail = true
            }
        }
    }
}
