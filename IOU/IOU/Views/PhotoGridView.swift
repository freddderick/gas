import SwiftUI

struct PhotoGridView: View {
    let receipts: [Receipt]
    let onSelect: (Receipt) -> Void

    private let columns = [
        GridItem(.adaptive(minimum: 110, maximum: 160), spacing: 4)
    ]

    var body: some View {
        LazyVGrid(columns: columns, spacing: 4) {
            ForEach(receipts) { receipt in
                Button {
                    onSelect(receipt)
                } label: {
                    GridTile(receipt: receipt)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(4)
    }
}

private struct GridTile: View {
    let receipt: Receipt

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            AsyncPhotoImage(assetIdentifier: receipt.assetIdentifier, targetSize: CGSize(width: 240, height: 240))
                .aspectRatio(1, contentMode: .fit)
                .clipped()

            LinearGradient(
                colors: [.black.opacity(0.55), .clear],
                startPoint: .bottom,
                endPoint: .top
            )
            .frame(height: 56)
            .frame(maxHeight: .infinity, alignment: .bottom)

            VStack(alignment: .leading, spacing: 1) {
                Text(receipt.merchant ?? "Receipt")
                    .font(.caption.weight(.semibold))
                    .lineLimit(1)
                Text(receipt.formattedAmount)
                    .font(.caption2)
            }
            .foregroundStyle(.white)
            .padding(6)
        }
        .background(Color.secondary.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
