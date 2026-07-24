import SwiftUI

/// Built-in receipt categories. Stored on `Receipt` by raw value so the enum
/// can grow without a migration; unknown raw values fall back to `.other`.
enum ReceiptCategory: String, CaseIterable, Codable, Identifiable {
    case groceries
    case dining
    case travel
    case transportation
    case shopping
    case utilities
    case entertainment
    case health
    case office
    case home
    case other

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .groceries: return "Groceries"
        case .dining: return "Dining"
        case .travel: return "Travel"
        case .transportation: return "Transportation"
        case .shopping: return "Shopping"
        case .utilities: return "Utilities"
        case .entertainment: return "Entertainment"
        case .health: return "Health"
        case .office: return "Office"
        case .home: return "Home"
        case .other: return "Other"
        }
    }

    var symbolName: String {
        switch self {
        case .groceries: return "cart.fill"
        case .dining: return "fork.knife"
        case .travel: return "airplane"
        case .transportation: return "car.fill"
        case .shopping: return "bag.fill"
        case .utilities: return "bolt.fill"
        case .entertainment: return "ticket.fill"
        case .health: return "cross.case.fill"
        case .office: return "printer.fill"
        case .home: return "house.fill"
        case .other: return "questionmark.circle.fill"
        }
    }

    var color: Color {
        switch self {
        case .groceries: return .green
        case .dining: return .orange
        case .travel: return .blue
        case .transportation: return .indigo
        case .shopping: return .pink
        case .utilities: return .yellow
        case .entertainment: return .purple
        case .health: return .red
        case .office: return .teal
        case .home: return .brown
        case .other: return .gray
        }
    }

    /// Very small keyword heuristic used to auto-suggest a category from OCR text.
    /// Users can always override the result, so this only needs to be "good enough".
    static func guess(fromText text: String, merchant: String?) -> ReceiptCategory {
        let haystack = ((merchant ?? "") + " " + text).lowercased()

        let keywordMap: [ReceiptCategory: [String]] = [
            .groceries: ["grocery", "market", "foods", "supermarket", "farm boy", "safeway", "kroger", "whole foods", "trader joe", "loblaws", "sobeys", "costco"],
            .dining: ["restaurant", "cafe", "coffee", "bar & grill", "bistro", "pizza", "starbucks", "mcdonald", "tim hortons", "diner", "eatery", "kitchen"],
            .travel: ["airlines", "airline", "hotel", "motel", "resort", "airbnb", "booking.com", "expedia", "flight", "airport"],
            .transportation: ["uber", "lyft", "taxi", "transit", "parking", "gas station", "fuel", "petro", "shell", "esso", "chevron"],
            .shopping: ["amazon", "walmart", "target", "mall", "store", "boutique", "apparel", "shoes", "electronics"],
            .utilities: ["hydro", "electric", "water bill", "internet", "telecom", "wireless", "utility", "gas bill"],
            .entertainment: ["cinema", "theatre", "theater", "movie", "concert", "netflix", "spotify", "game", "amusement"],
            .health: ["pharmacy", "clinic", "hospital", "dental", "doctor", "drugstore", "cvs", "walgreens", "shoppers drug mart"],
            .office: ["office depot", "staples", "office supply", "print", "stationery"],
            .home: ["home depot", "lowe's", "lowes", "hardware", "furniture", "ikea", "renovation"]
        ]

        for (category, keywords) in keywordMap {
            if keywords.contains(where: { haystack.contains($0) }) {
                return category
            }
        }
        return .other
    }
}
