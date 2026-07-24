import Photos
import SwiftData
import UIKit

/// State published while a library scan is running, so the UI can show progress.
struct ScanProgress: Equatable {
    var scanned: Int
    var total: Int
    var found: Int
    var isRunning: Bool

    static let idle = ScanProgress(scanned: 0, total: 0, found: 0, isRunning: false)
}

/// Scans the photo library for images that look like receipts and imports
/// them into SwiftData. Already-scanned assets are tracked in `UserDefaults`
/// so re-running a scan only looks at photos added since the last pass.
@Observable
final class ReceiptImportManager {
    private(set) var progress: ScanProgress = .idle

    private let processedIdentifiersKey = "IOU.processedAssetIdentifiers"
    private var processedIdentifiers: Set<String> {
        get { Set(UserDefaults.standard.stringArray(forKey: processedIdentifiersKey) ?? []) }
        set { UserDefaults.standard.set(Array(newValue), forKey: processedIdentifiersKey) }
    }

    /// Scans new (not-yet-processed) photos in the library, imports any that
    /// look like receipts, and records every scanned asset so it isn't
    /// re-processed next time. Runs OCR concurrently with a small task group.
    @MainActor
    func scanLibrary(context: ModelContext, fullRescan: Bool = false) async {
        guard progress.isRunning == false else { return }

        let fetchOptions = PHFetchOptions()
        fetchOptions.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        let allPhotos = PHAsset.fetchAssets(with: .image, options: fetchOptions)

        var alreadyProcessed = fullRescan ? Set<String>() : processedIdentifiers
        var assetsToScan: [PHAsset] = []
        allPhotos.enumerateObjects { asset, _, _ in
            if !alreadyProcessed.contains(asset.localIdentifier) {
                assetsToScan.append(asset)
            }
        }

        guard !assetsToScan.isEmpty else { return }

        progress = ScanProgress(scanned: 0, total: assetsToScan.count, found: 0, isRunning: true)

        var foundCount = 0
        let batchSize = 6
        for batchStart in stride(from: 0, to: assetsToScan.count, by: batchSize) {
            let batch = Array(assetsToScan[batchStart..<min(batchStart + batchSize, assetsToScan.count)])

            await withTaskGroup(of: (PHAsset, ReceiptOCRResult?).self) { group in
                for asset in batch {
                    group.addTask {
                        guard let image = await PhotoImageLoader.shared.fullImage(for: asset) else {
                            return (asset, nil)
                        }
                        let result = try? await ReceiptOCRService.recognizeText(in: image)
                        return (asset, result)
                    }
                }

                for await (asset, result) in group {
                    alreadyProcessed.insert(asset.localIdentifier)

                    if let result, result.looksLikeReceipt {
                        let merchant = result.merchant
                        let category = ReceiptCategory.guess(fromText: result.rawText, merchant: merchant)
                        let receipt = Receipt(
                            assetIdentifier: asset.localIdentifier,
                            date: result.purchaseDate ?? asset.creationDate ?? Date(),
                            amountValue: result.totalAmount.map { NSDecimalNumber(decimal: $0).doubleValue },
                            merchant: merchant,
                            category: category,
                            ocrText: result.rawText,
                            assetCreationDate: asset.creationDate ?? Date()
                        )
                        context.insert(receipt)
                        foundCount += 1
                    }

                    progress.scanned += 1
                    progress.found = foundCount
                }
            }

            // Persist incrementally so a large library scan isn't lost if interrupted.
            try? context.save()
            processedIdentifiers = alreadyProcessed
        }

        try? context.save()
        processedIdentifiers = alreadyProcessed
        progress.isRunning = false
    }

    /// Manually add a specific photo as a receipt (e.g. picked via `PhotosPicker`),
    /// bypassing the "looks like a receipt" heuristic since the user chose it explicitly.
    @MainActor
    func addManualReceipt(assetIdentifier: String, context: ModelContext) async {
        guard let asset = PhotoImageLoader.shared.fetchAsset(for: assetIdentifier) else { return }
        guard let image = await PhotoImageLoader.shared.fullImage(for: asset) else { return }
        let result = try? await ReceiptOCRService.recognizeText(in: image)

        let merchant = result?.merchant
        let category = ReceiptCategory.guess(fromText: result?.rawText ?? "", merchant: merchant)
        let receipt = Receipt(
            assetIdentifier: assetIdentifier,
            date: result?.purchaseDate ?? asset.creationDate ?? Date(),
            amountValue: result?.totalAmount.map { NSDecimalNumber(decimal: $0).doubleValue },
            merchant: merchant,
            category: category,
            ocrText: result?.rawText ?? "",
            assetCreationDate: asset.creationDate ?? Date(),
            isManuallyTagged: true
        )
        context.insert(receipt)
        try? context.save()

        var processed = processedIdentifiers
        processed.insert(assetIdentifier)
        processedIdentifiers = processed
    }

    func resetScanHistory() {
        UserDefaults.standard.removeObject(forKey: processedIdentifiersKey)
    }
}
