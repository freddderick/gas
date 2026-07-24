import SwiftUI

struct CategoryBadge: View {
    let category: ReceiptCategory
    var compact: Bool = false

    var body: some View {
        Label(category.displayName, systemImage: category.symbolName)
            .font(compact ? .caption2 : .caption)
            .fontWeight(.medium)
            .padding(.horizontal, compact ? 6 : 8)
            .padding(.vertical, compact ? 3 : 4)
            .background(category.color.opacity(0.18), in: Capsule())
            .foregroundStyle(category.color)
    }
}
