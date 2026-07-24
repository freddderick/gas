import SwiftUI

struct ScanProgressBanner: View {
    let progress: ScanProgress

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                ProgressView()
                    .controlSize(.small)
                Text("Scanning photo library…")
                    .font(.footnote.weight(.medium))
                Spacer()
                Text("\(progress.found) found")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            ProgressView(value: Double(progress.scanned), total: Double(max(progress.total, 1)))
                .tint(.accentColor)
        }
        .padding(12)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal)
    }
}
