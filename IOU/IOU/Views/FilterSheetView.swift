import SwiftUI

struct FilterSheetView: View {
    @Bindable var viewModel: GalleryViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Date Range") {
                    Picker("Date Range", selection: $viewModel.datePreset) {
                        ForEach(DateFilterPreset.allCases) { preset in
                            Text(preset.displayName).tag(preset)
                        }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()

                    if viewModel.datePreset == .custom {
                        DatePicker(
                            "Start",
                            selection: Binding(
                                get: { viewModel.customDateRange.lowerBound },
                                set: { newValue in
                                    viewModel.customDateRange = newValue...max(newValue, viewModel.customDateRange.upperBound)
                                }
                            ),
                            displayedComponents: .date
                        )
                        DatePicker(
                            "End",
                            selection: Binding(
                                get: { viewModel.customDateRange.upperBound },
                                set: { newValue in
                                    viewModel.customDateRange = min(viewModel.customDateRange.lowerBound, newValue)...newValue
                                }
                            ),
                            displayedComponents: .date
                        )
                    }
                }

                Section("Categories") {
                    ForEach(ReceiptCategory.allCases) { category in
                        Button {
                            toggle(category)
                        } label: {
                            HStack {
                                CategoryBadge(category: category)
                                Spacer()
                                if viewModel.selectedCategories.contains(category) {
                                    Image(systemName: "checkmark")
                                        .foregroundStyle(.tint)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }

                Section("Sort By") {
                    Picker("Sort By", selection: $viewModel.sortOption) {
                        ForEach(SortOption.allCases) { option in
                            Text(option.displayName).tag(option)
                        }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                }
            }
            .navigationTitle("Filters")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Clear") { viewModel.clearFilters() }
                        .disabled(!viewModel.hasActiveFilters)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func toggle(_ category: ReceiptCategory) {
        if viewModel.selectedCategories.contains(category) {
            viewModel.selectedCategories.remove(category)
        } else {
            viewModel.selectedCategories.insert(category)
        }
    }
}
