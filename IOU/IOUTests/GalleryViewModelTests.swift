import XCTest
@testable import IOU

final class GalleryViewModelTests: XCTestCase {
    private func makeReceipt(
        id: String,
        merchant: String,
        amount: Double?,
        category: ReceiptCategory,
        daysAgo: Int,
        ocrText: String = ""
    ) -> Receipt {
        Receipt(
            assetIdentifier: id,
            date: Calendar.current.date(byAdding: .day, value: -daysAgo, to: Date())!,
            amountValue: amount,
            merchant: merchant,
            category: category,
            ocrText: ocrText,
            assetCreationDate: Date()
        )
    }

    func testSearchMatchesMerchantCaseInsensitively() {
        let receipts = [
            makeReceipt(id: "1", merchant: "Starbucks", amount: 5.25, category: .dining, daysAgo: 1),
            makeReceipt(id: "2", merchant: "Home Depot", amount: 45.00, category: .home, daysAgo: 2)
        ]
        let viewModel = GalleryViewModel()
        viewModel.searchText = "starbucks"

        let results = viewModel.apply(to: receipts)
        XCTAssertEqual(results.map(\.assetIdentifier), ["1"])
    }

    func testSearchByAmountMatchesTotal() {
        let receipts = [
            makeReceipt(id: "1", merchant: "Starbucks", amount: 5.25, category: .dining, daysAgo: 1),
            makeReceipt(id: "2", merchant: "Home Depot", amount: 45.00, category: .home, daysAgo: 2)
        ]
        let viewModel = GalleryViewModel()
        viewModel.searchText = "45.00"

        let results = viewModel.apply(to: receipts)
        XCTAssertEqual(results.map(\.assetIdentifier), ["2"])
    }

    func testSearchByAmountMatchesLineItemInOCRText() {
        let receipts = [
            makeReceipt(id: "1", merchant: "Grocer", amount: 57.00, category: .groceries, daysAgo: 1, ocrText: "milk 3.99\nbread 2.49\ntotal 57.00")
        ]
        let viewModel = GalleryViewModel()
        viewModel.searchText = "3.99"

        let results = viewModel.apply(to: receipts)
        XCTAssertEqual(results.count, 1)
    }

    func testCategoryFilterNarrowsResults() {
        let receipts = [
            makeReceipt(id: "1", merchant: "Starbucks", amount: 5.25, category: .dining, daysAgo: 1),
            makeReceipt(id: "2", merchant: "Home Depot", amount: 45.00, category: .home, daysAgo: 2)
        ]
        let viewModel = GalleryViewModel()
        viewModel.selectedCategories = [.dining]

        let results = viewModel.apply(to: receipts)
        XCTAssertEqual(results.map(\.assetIdentifier), ["1"])
    }

    func testDateFilterThisWeekExcludesOlderReceipts() {
        let receipts = [
            makeReceipt(id: "1", merchant: "Recent", amount: 10, category: .other, daysAgo: 1),
            makeReceipt(id: "2", merchant: "Old", amount: 10, category: .other, daysAgo: 40)
        ]
        let viewModel = GalleryViewModel()
        viewModel.datePreset = .thisWeek

        let results = viewModel.apply(to: receipts)
        XCTAssertEqual(results.map(\.assetIdentifier), ["1"])
    }

    func testSortByAmountDescending() {
        let receipts = [
            makeReceipt(id: "1", merchant: "A", amount: 10, category: .other, daysAgo: 1),
            makeReceipt(id: "2", merchant: "B", amount: 90, category: .other, daysAgo: 2),
            makeReceipt(id: "3", merchant: "C", amount: 40, category: .other, daysAgo: 3)
        ]
        let viewModel = GalleryViewModel()
        viewModel.sortOption = .amountDescending

        let results = viewModel.apply(to: receipts)
        XCTAssertEqual(results.map(\.assetIdentifier), ["2", "3", "1"])
    }

    func testClearFiltersResetsCategoryAndDate() {
        let viewModel = GalleryViewModel()
        viewModel.selectedCategories = [.dining]
        viewModel.datePreset = .thisMonth

        viewModel.clearFilters()

        XCTAssertTrue(viewModel.selectedCategories.isEmpty)
        XCTAssertEqual(viewModel.datePreset, .all)
        XCTAssertFalse(viewModel.hasActiveFilters)
    }
}
