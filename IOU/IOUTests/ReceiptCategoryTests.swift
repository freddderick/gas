import XCTest
@testable import IOU

final class ReceiptCategoryTests: XCTestCase {
    func testGuessesGroceriesFromMerchant() {
        let category = ReceiptCategory.guess(fromText: "", merchant: "Trader Joe's #123")
        XCTAssertEqual(category, .groceries)
    }

    func testGuessesDiningFromText() {
        let category = ReceiptCategory.guess(fromText: "welcome to starbucks coffee", merchant: nil)
        XCTAssertEqual(category, .dining)
    }

    func testGuessesTransportationForGasStation() {
        let category = ReceiptCategory.guess(fromText: "shell gas station pump 4", merchant: nil)
        XCTAssertEqual(category, .transportation)
    }

    func testFallsBackToOtherWhenNoKeywordMatches() {
        let category = ReceiptCategory.guess(fromText: "some random unrelated text", merchant: "Bob's Widgets")
        XCTAssertEqual(category, .other)
    }

    func testUnknownRawValueFallsBackToOtherOnReceipt() {
        let receipt = Receipt(
            assetIdentifier: "asset-1",
            date: Date(),
            amountValue: 10,
            merchant: "Test",
            category: .other,
            ocrText: "",
            assetCreationDate: Date()
        )
        receipt.categoryRawValue = "not-a-real-category"
        XCTAssertEqual(receipt.category, .other)
    }
}
