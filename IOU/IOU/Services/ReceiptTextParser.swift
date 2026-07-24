import Foundation

struct ParsedReceiptText {
    let looksLikeReceipt: Bool
    let totalAmount: Decimal?
    let purchaseDate: Date?
    let merchant: String?
}

/// Pure text-processing heuristics used to turn OCR'd receipt lines into
/// structured data. Kept free of Vision/UIKit so it can be unit tested with
/// plain string fixtures instead of real photos.
enum ReceiptTextParser {
    /// Words that make an image very likely to be a receipt when found near
    /// a currency amount. Keeps a passport photo of your lunch from becoming
    /// a "receipt" just because it contains a dollar sign somewhere.
    static let receiptKeywords = [
        "total", "subtotal", "tax", "receipt", "amount due", "balance due",
        "cash", "change due", "visa", "mastercard", "debit", "credit card",
        "thank you for", "invoice", "order #", "qty", "item", "tip"
    ]

    static func parse(lines: [String], referenceDate: Date = Date()) -> ParsedReceiptText {
        let rawText = lines.joined(separator: "\n")
        let lowered = rawText.lowercased()

        let amounts = extractAmounts(from: lines)
        let hasCurrency = !amounts.isEmpty
        let keywordHits = receiptKeywords.filter { lowered.contains($0) }.count
        let looksLikeReceipt = hasCurrency && keywordHits >= 1

        return ParsedReceiptText(
            looksLikeReceipt: looksLikeReceipt,
            totalAmount: bestTotal(amounts: amounts),
            purchaseDate: extractDate(from: lines, referenceDate: referenceDate),
            merchant: guessMerchant(from: lines)
        )
    }

    // MARK: - Amount extraction

    private static let amountRegex = try! NSRegularExpression(
        pattern: #"(?:[$€£]\s?)(\d{1,3}(?:[,.]\d{3})*[.,]\d{2})|(\d{1,3}(?:[,.]\d{3})*[.,]\d{2})\s?(?:[$€£])"#
    )

    struct LineAmount {
        let line: String
        let value: Decimal
    }

    static func extractAmounts(from lines: [String]) -> [LineAmount] {
        var results: [LineAmount] = []
        for line in lines {
            let ns = line as NSString
            let matches = amountRegex.matches(in: line, range: NSRange(location: 0, length: ns.length))
            for match in matches {
                for groupIndex in 1..<match.numberOfRanges {
                    let range = match.range(at: groupIndex)
                    guard range.location != NSNotFound else { continue }
                    let numberString = ns.substring(with: range)
                        .replacingOccurrences(of: ",", with: "")
                    if let value = Decimal(string: numberString) {
                        results.append(LineAmount(line: line.lowercased(), value: value))
                    }
                }
            }
        }
        return results
    }

    /// Prefers a line containing "total" (but not "subtotal") over the raw
    /// maximum amount found, since receipts often list many smaller line items.
    static func bestTotal(amounts: [LineAmount]) -> Decimal? {
        guard !amounts.isEmpty else { return nil }

        if let grandTotal = amounts.first(where: {
            $0.line.contains("total") && !$0.line.contains("subtotal")
        }) {
            return grandTotal.value
        }
        if let balanceDue = amounts.first(where: { $0.line.contains("balance due") || $0.line.contains("amount due") }) {
            return balanceDue.value
        }
        return amounts.map(\.value).max()
    }

    // MARK: - Date extraction

    private static let dateDetector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.date.rawValue)

    static func extractDate(from lines: [String], referenceDate: Date = Date()) -> Date? {
        let calendar = Calendar.current

        for line in lines {
            guard let detector = dateDetector else { break }
            let ns = line as NSString
            let matches = detector.matches(in: line, range: NSRange(location: 0, length: ns.length))
            for match in matches {
                guard let date = match.date else { continue }
                // Reject obviously-wrong matches (e.g. a "12:30" time misread as a date,
                // or a date far in the future from a mis-scanned year).
                if date <= referenceDate.addingTimeInterval(60 * 60 * 24),
                   let yearsAgo = calendar.dateComponents([.year], from: date, to: referenceDate).year,
                   yearsAgo >= 0, yearsAgo < 15 {
                    return date
                }
            }
        }
        return nil
    }

    // MARK: - Merchant guess

    static func guessMerchant(from lines: [String]) -> String? {
        // The merchant name is almost always one of the first few non-empty lines,
        // and rarely starts with a digit or currency symbol.
        for line in lines.prefix(6) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard trimmed.count >= 3 else { continue }
            guard let first = trimmed.first, !first.isNumber, first != "$" else { continue }
            let letterCount = trimmed.filter(\.isLetter).count
            guard letterCount >= 3 else { continue }
            return trimmed
        }
        return nil
    }
}
