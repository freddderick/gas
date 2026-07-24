import Foundation

enum GalleryViewMode: String, CaseIterable {
    case grid
    case list

    var symbolName: String {
        switch self {
        case .grid: return "square.grid.2x2"
        case .list: return "list.bullet"
        }
    }
}

enum SortOption: String, CaseIterable, Identifiable {
    case dateDescending
    case dateAscending
    case amountDescending
    case amountAscending
    case merchant

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .dateDescending: return "Newest First"
        case .dateAscending: return "Oldest First"
        case .amountDescending: return "Highest Amount"
        case .amountAscending: return "Lowest Amount"
        case .merchant: return "Merchant (A–Z)"
        }
    }
}

enum DateFilterPreset: String, CaseIterable, Identifiable {
    case all
    case thisWeek
    case thisMonth
    case thisYear
    case custom

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .all: return "All Time"
        case .thisWeek: return "This Week"
        case .thisMonth: return "This Month"
        case .thisYear: return "This Year"
        case .custom: return "Custom Range"
        }
    }

    func range(referenceDate: Date = Date(), calendar: Calendar = .current) -> ClosedRange<Date>? {
        switch self {
        case .all:
            return nil
        case .thisWeek:
            guard let start = calendar.dateInterval(of: .weekOfYear, for: referenceDate) else { return nil }
            return start.start...min(start.end, referenceDate)
        case .thisMonth:
            guard let start = calendar.dateInterval(of: .month, for: referenceDate) else { return nil }
            return start.start...min(start.end, referenceDate)
        case .thisYear:
            guard let start = calendar.dateInterval(of: .year, for: referenceDate) else { return nil }
            return start.start...min(start.end, referenceDate)
        case .custom:
            return nil
        }
    }
}

/// Drives the gallery's search, filter, and sort state. Views hand it the raw
/// `[Receipt]` array from a SwiftData `@Query` and read back `apply(to:)`.
@Observable
final class GalleryViewModel {
    var viewMode: GalleryViewMode = .grid
    var searchText: String = ""
    var selectedCategories: Set<ReceiptCategory> = []
    var datePreset: DateFilterPreset = .all
    var customDateRange: ClosedRange<Date> = Calendar.current.date(byAdding: .month, value: -1, to: Date())!...Date()
    var sortOption: SortOption = .dateDescending

    var hasActiveFilters: Bool {
        !selectedCategories.isEmpty || datePreset != .all
    }

    func clearFilters() {
        selectedCategories.removeAll()
        datePreset = .all
    }

    private var effectiveDateRange: ClosedRange<Date>? {
        datePreset == .custom ? customDateRange : datePreset.range()
    }

    func apply(to receipts: [Receipt]) -> [Receipt] {
        var results = receipts

        if let range = effectiveDateRange {
            results = results.filter { range.contains($0.date) }
        }

        if !selectedCategories.isEmpty {
            results = results.filter { selectedCategories.contains($0.category) }
        }

        let trimmedSearch = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmedSearch.isEmpty {
            results = results.filter { matches(receipt: $0, query: trimmedSearch) }
        }

        return sort(results)
    }

    /// A search query matches if it appears in the merchant name, in the OCR'd
    /// receipt text (so any line-item amount or word on the receipt is
    /// searchable), or as a numeric match against the parsed total amount.
    private func matches(receipt: Receipt, query: String) -> Bool {
        let lowerQuery = query.lowercased()

        if let merchant = receipt.merchant, merchant.lowercased().contains(lowerQuery) {
            return true
        }
        if receipt.ocrText.contains(lowerQuery) {
            return true
        }
        if !receipt.notes.isEmpty, receipt.notes.lowercased().contains(lowerQuery) {
            return true
        }

        let normalizedQuery = query
            .replacingOccurrences(of: "$", with: "")
            .trimmingCharacters(in: .whitespaces)
        if let queryAmount = Decimal(string: normalizedQuery) {
            if let amount = receipt.amount, isClose(amount, queryAmount) {
                return true
            }
            // Also catch the amount appearing as a line item anywhere in the OCR text,
            // even if it wasn't picked as the grand total.
            if receipt.ocrText.contains(normalizedQuery) {
                return true
            }
        }

        return false
    }

    private func isClose(_ a: Decimal, _ b: Decimal, tolerance: Decimal = Decimal(string: "0.01")!) -> Bool {
        abs(a - b) <= tolerance
    }

    private func sort(_ receipts: [Receipt]) -> [Receipt] {
        switch sortOption {
        case .dateDescending:
            return receipts.sorted { $0.date > $1.date }
        case .dateAscending:
            return receipts.sorted { $0.date < $1.date }
        case .amountDescending:
            return receipts.sorted { ($0.amount ?? 0) > ($1.amount ?? 0) }
        case .amountAscending:
            return receipts.sorted { ($0.amount ?? 0) < ($1.amount ?? 0) }
        case .merchant:
            return receipts.sorted {
                ($0.merchant ?? "zzzz").localizedCaseInsensitiveCompare($1.merchant ?? "zzzz") == .orderedAscending
            }
        }
    }
}
