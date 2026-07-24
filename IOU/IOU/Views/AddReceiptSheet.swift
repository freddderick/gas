import SwiftUI
import PhotosUI
import SwiftData

/// Lets the user manually pick a photo from their library and tag it as a
/// receipt, for the cases the automatic scan heuristic misses.
struct AddReceiptSheet: View {
    let importManager: ReceiptImportManager
    @Environment(\.modelContext) private var modelContext
    @Environment(\.dismiss) private var dismiss

    @State private var selection: PhotosPickerItem?
    @State private var isImporting = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Image(systemName: "photo.badge.plus")
                    .font(.system(size: 48))
                    .foregroundStyle(.tint)

                Text("Pick a photo of a receipt from your library. IOU will read the text on-device and file it away.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                PhotosPicker(selection: $selection, matching: .images) {
                    Label("Choose Photo", systemImage: "photo.on.rectangle")
                        .frame(maxWidth: 260)
                }
                .buttonStyle(.borderedProminent)
                .disabled(isImporting)

                if isImporting {
                    ProgressView("Reading receipt…")
                }

                Spacer()
            }
            .padding(.top, 32)
            .navigationTitle("Add Receipt")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .onChange(of: selection) { _, newValue in
                guard let newValue else { return }
                Task { await importPicked(newValue) }
            }
        }
    }

    private func importPicked(_ item: PhotosPickerItem) async {
        guard let identifier = item.itemIdentifier else { return }
        isImporting = true
        await importManager.addManualReceipt(assetIdentifier: identifier, context: modelContext)
        isImporting = false
        dismiss()
    }
}
