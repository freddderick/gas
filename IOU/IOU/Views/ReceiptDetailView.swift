import SwiftUI
import SwiftData

struct ReceiptDetailView: View {
    @Bindable var receipt: Receipt
    @Environment(\.modelContext) private var modelContext
    @Environment(\.dismiss) private var dismiss

    @State private var amountText: String = ""
    @State private var showDeleteConfirmation = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                AsyncPhotoImage(
                    assetIdentifier: receipt.assetIdentifier,
                    targetSize: CGSize(width: 900, height: 900),
                    contentMode: .fit
                )
                .frame(maxWidth: .infinity)
                .frame(height: 360)
                .background(Color.black.opacity(0.05))
                .clipShape(RoundedRectangle(cornerRadius: 12))

                VStack(alignment: .leading, spacing: 16) {
                    LabeledContent("Merchant") {
                        TextField("Merchant", text: Binding(
                            get: { receipt.merchant ?? "" },
                            set: { receipt.merchant = $0.isEmpty ? nil : $0 }
                        ))
                        .multilineTextAlignment(.trailing)
                    }

                    LabeledContent("Amount") {
                        TextField("0.00", text: $amountText)
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                            .onChange(of: amountText) { _, newValue in
                                receipt.amount = Decimal(string: newValue)
                            }
                    }

                    DatePicker("Date", selection: $receipt.date, displayedComponents: .date)

                    Picker("Category", selection: Binding(
                        get: { receipt.category },
                        set: { receipt.category = $0 }
                    )) {
                        ForEach(ReceiptCategory.allCases) { category in
                            Label(category.displayName, systemImage: category.symbolName).tag(category)
                        }
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Notes")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        TextField("Add a note…", text: $receipt.notes, axis: .vertical)
                            .lineLimit(3...6)
                            .textFieldStyle(.roundedBorder)
                    }
                }
                .padding()
                .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))

                DisclosureGroup("Recognized Text") {
                    Text(receipt.ocrText.isEmpty ? "No text recognized." : receipt.ocrText)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                .padding()
                .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))

                Button(role: .destructive) {
                    showDeleteConfirmation = true
                } label: {
                    Label("Remove from IOU", systemImage: "trash")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .tint(.red)
            }
            .padding()
        }
        .navigationTitle(receipt.merchant ?? "Receipt")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            receipt.isReviewed = true
            amountText = receipt.amount.map { "\($0)" } ?? ""
        }
        .confirmationDialog(
            "Remove this receipt from IOU?",
            isPresented: $showDeleteConfirmation,
            titleVisibility: .visible
        ) {
            Button("Remove", role: .destructive) {
                modelContext.delete(receipt)
                dismiss()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("The photo stays in your Photos library. This only removes it from IOU.")
        }
    }
}
