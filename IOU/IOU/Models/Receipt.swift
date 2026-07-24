import Foundation
import SwiftData

/// A receipt discovered in (or manually added to) the user's photo library.
///
/// `assetIdentifier` links back to the `PHAsset` in Photos; IOU never copies
/// the original image, it only stores extracted metadata plus the OCR text
/// so amounts and merchants can be searched without re-running Vision.
@Model
final class Receipt {
    @Attribute(.unique) var assetIdentifier: String

    /// The best-guess date for the purchase (parsed from the receipt text,
    /// falling back to the photo's creation date).
    var date: Date

    /// Amount in the receipt's minor currency units avoided; stored as Decimal via String
    /// because SwiftData does not natively support Decimal predicates on all platforms.
    var amountValue: Double?

    var merchant: String?

    var categoryRawValue: String

    /// Full text recognized by Vision, lowercased, used for free-text / amount search.
    var ocrText: String

    var notes: String

    /// When Photos itself created the asset (used as a fallback and for sorting
    /// when no date could be parsed from the receipt text).
    var assetCreationDate: Date

    /// True once the user has looked at / confirmed this receipt at least once.
    var isReviewed: Bool

    /// True if the user manually added this receipt (vs. auto-detected during a scan).
    var isManuallyTagged: Bool

    var createdAt: Date

    init(
        assetIdentifier: String,
        date: Date,
        amountValue: Double?,
        merchant: String?,
        category: ReceiptCategory,
        ocrText: String,
        notes: String = "",
        assetCreationDate: Date,
        isReviewed: Bool = false,
        isManuallyTagged: Bool = false
    ) {
        self.assetIdentifier = assetIdentifier
        self.date = date
        self.amountValue = amountValue
        self.merchant = merchant
        self.categoryRawValue = category.rawValue
        self.ocrText = ocrText
        self.notes = notes
        self.assetCreationDate = assetCreationDate
        self.isReviewed = isReviewed
        self.isManuallyTagged = isManuallyTagged
        self.createdAt = Date()
    }

    var category: ReceiptCategory {
        get { ReceiptCategory(rawValue: categoryRawValue) ?? .other }
        set { categoryRawValue = newValue.rawValue }
    }

    var amount: Decimal? {
        get { amountValue.map { Decimal($0) } }
        set { amountValue = newValue.map { NSDecimalNumber(decimal: $0).doubleValue } }
    }

    var formattedAmount: String {
        guard let amount else { return "—" }
        return amount.formatted(.currency(code: Locale.current.currency?.identifier ?? "USD"))
    }
}
