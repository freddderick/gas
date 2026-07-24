import SwiftUI

struct ReceiptListView: View {
    let receipts: [Receipt]
    let onSelect: (Receipt) -> Void

    var body: some View {
        List(receipts) { receipt in
            Button {
                onSelect(receipt)
            } label: {
                ReceiptRow(receipt: receipt)
            }
            .buttonStyle(.plain)
            .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
        }
        .listStyle(.plain)
    }
}

private struct ReceiptRow: View {
    let receipt: Receipt

    var body: some View {
        HStack(spacing: 12) {
            AsyncPhotoImage(assetIdentifier: receipt.assetIdentifier, targetSize: CGSize(width: 120, height: 120))
                .frame(width: 56, height: 56)
                .clipShape(RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 4) {
                Text(receipt.merchant ?? "Unknown Merchant")
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                Text(receipt.date.formatted(date: .abbreviated, time: .omitted))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                CategoryBadge(category: receipt.category, compact: true)
            }

            Spacer()

            Text(receipt.formattedAmount)
                .font(.subheadline.weight(.semibold))
                .monospacedDigit()
        }
        .contentShape(Rectangle())
    }
}
