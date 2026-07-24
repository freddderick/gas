import XCTest
@testable import IOU

final class ReceiptTextParserTests: XCTestCase {
    func testDetectsObviousReceipt() {
        let lines = [
            "TRADER JOE'S #123",
            "BANANAS         1.99",
            "BREAD           3.49",
            "SUBTOTAL        5.48",
            "TAX             0.44",
            "TOTAL          $5.92",
            "VISA ****1234",
            "THANK YOU FOR SHOPPING"
        ]

        let result = ReceiptTextParser.parse(lines: lines)

        XCTAssertTrue(result.looksLikeReceipt)
        XCTAssertEqual(result.totalAmount, Decimal(string: "5.92"))
        XCTAssertEqual(result.merchant, "TRADER JOE'S #123")
    }

    func testRejectsNonReceiptText() {
        let lines = [
            "Happy Birthday!",
            "Wishing you an amazing day",
            "Love, the family"
        ]

        let result = ReceiptTextParser.parse(lines: lines)

        XCTAssertFalse(result.looksLikeReceipt)
        XCTAssertNil(result.totalAmount)
    }

    func testRequiresBothCurrencyAndKeyword() {
        // Has a dollar amount but no receipt-ish keywords: should not qualify.
        let lines = ["I found $20.00 on the sidewalk today, lucky me!"]
        let result = ReceiptTextParser.parse(lines: lines)
        XCTAssertFalse(result.looksLikeReceipt)
    }

    func testPrefersTotalOverSubtotalAndLineItems() {
        let lines = [
            "ITEM A    12.00",
            "ITEM B    45.00",
            "SUBTOTAL  57.00",
            "TAX        4.56",
            "TOTAL     61.56"
        ]
        let amounts = ReceiptTextParser.extractAmounts(from: lines)
        let total = ReceiptTextParser.bestTotal(amounts: amounts)
        XCTAssertEqual(total, Decimal(string: "61.56"))
    }

    func testFallsBackToMaxAmountWhenNoTotalLine() {
        let lines = ["ITEM A 12.00", "ITEM B 45.00"]
        let amounts = ReceiptTextParser.extractAmounts(from: lines)
        let total = ReceiptTextParser.bestTotal(amounts: amounts)
        XCTAssertEqual(total, Decimal(string: "45.00"))
    }

    func testExtractsAmountWithTrailingDollarSign() {
        let amounts = ReceiptTextParser.extractAmounts(from: ["24.99$"])
        XCTAssertEqual(amounts.first?.value, Decimal(string: "24.99"))
    }

    func testExtractsAmountWithThousandsSeparator() {
        let amounts = ReceiptTextParser.extractAmounts(from: ["Total: $1,234.56"])
        XCTAssertEqual(amounts.first?.value, Decimal(string: "1234.56"))
    }

    func testExtractDateIgnoresFutureAndOldDates() {
        let reference = ISO8601DateFormatter().date(from: "2026-07-24T00:00:00Z")!

        // A plausible recent date should be picked up.
        let recent = ReceiptTextParser.extractDate(from: ["Purchase date: 03/14/2026"], referenceDate: reference)
        XCTAssertNotNil(recent)

        // A date far in the future (garbled OCR) should be rejected.
        let future = ReceiptTextParser.extractDate(from: ["Purchase date: 03/14/2099"], referenceDate: reference)
        XCTAssertNil(future)
    }

    func testGuessMerchantSkipsNumericAndShortLines() {
        let lines = ["12345", "#", "AC", "Corner Bakery Cafe", "123 Main St"]
        XCTAssertEqual(ReceiptTextParser.guessMerchant(from: lines), "Corner Bakery Cafe")
    }
}
