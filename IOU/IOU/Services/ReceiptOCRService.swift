import Vision
import UIKit

struct ReceiptOCRResult {
    let rawText: String
    let lines: [String]
    let looksLikeReceipt: Bool
    let totalAmount: Decimal?
    let purchaseDate: Date?
    let merchant: String?
}

/// Runs on-device text recognition (Vision) over a receipt photo, then hands
/// the recognized lines to `ReceiptTextParser` to decide whether the image is
/// actually a receipt and to pull out an amount / date / merchant guess.
enum ReceiptOCRService {
    static func recognizeText(in image: UIImage) async throws -> ReceiptOCRResult {
        guard let cgImage = image.cgImage else {
            return ReceiptOCRResult(rawText: "", lines: [], looksLikeReceipt: false, totalAmount: nil, purchaseDate: nil, merchant: nil)
        }

        let observations: [VNRecognizedTextObservation] = try await withCheckedThrowingContinuation { continuation in
            let request = VNRecognizeTextRequest { request, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }
                continuation.resume(returning: (request.results as? [VNRecognizedTextObservation]) ?? [])
            }
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = true

            let handler = VNImageRequestHandler(cgImage: cgImage, orientation: cgOrientation(from: image.imageOrientation))
            do {
                try handler.perform([request])
            } catch {
                continuation.resume(throwing: error)
            }
        }

        let lines = observations.compactMap { $0.topCandidates(1).first?.string }
        let parsed = ReceiptTextParser.parse(lines: lines)

        return ReceiptOCRResult(
            rawText: lines.joined(separator: "\n").lowercased(),
            lines: lines,
            looksLikeReceipt: parsed.looksLikeReceipt,
            totalAmount: parsed.totalAmount,
            purchaseDate: parsed.purchaseDate,
            merchant: parsed.merchant
        )
    }

    private static func cgOrientation(from orientation: UIImage.Orientation) -> CGImagePropertyOrientation {
        switch orientation {
        case .up: return .up
        case .down: return .down
        case .left: return .left
        case .right: return .right
        case .upMirrored: return .upMirrored
        case .downMirrored: return .downMirrored
        case .leftMirrored: return .leftMirrored
        case .rightMirrored: return .rightMirrored
        @unknown default: return .up
        }
    }
}
