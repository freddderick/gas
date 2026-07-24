import SwiftUI
import SwiftData

struct GalleryView: View {
    @Query private var allReceipts: [Receipt]

    let importManager: ReceiptImportManager
    @Environment(\.modelContext) private var modelContext

    @State private var viewModel = GalleryViewModel()
    @State private var showFilters = false
    @State private var showAddReceipt = false
    @State private var selectedReceipt: Receipt?

    init(importManager: ReceiptImportManager, sort: [SortDescriptor<Receipt>] = [SortDescriptor(\Receipt.date, order: .reverse)]) {
        self.importManager = importManager
        _allReceipts = Query(sort: sort)
    }

    private var filteredReceipts: [Receipt] {
        viewModel.apply(to: allReceipts)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if importManager.progress.isRunning {
                    ScanProgressBanner(progress: importManager.progress)
                        .padding(.vertical, 8)
                }

                if allReceipts.isEmpty && !importManager.progress.isRunning {
                    emptyState
                } else if filteredReceipts.isEmpty {
                    noResultsState
                } else {
                    switch viewModel.viewMode {
                    case .grid:
                        ScrollView {
                            PhotoGridView(receipts: filteredReceipts) { selectedReceipt = $0 }
                        }
                    case .list:
                        ReceiptListView(receipts: filteredReceipts) { selectedReceipt = $0 }
                    }
                }
            }
            .navigationTitle("IOU")
            .searchable(text: $viewModel.searchText, prompt: "Search merchant, notes, or an amount")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Menu {
                        Button {
                            Task { await importManager.scanLibrary(context: modelContext) }
                        } label: {
                            Label("Scan for New Receipts", systemImage: "arrow.clockwise")
                        }
                        Button {
                            Task { await importManager.scanLibrary(context: modelContext, fullRescan: true) }
                        } label: {
                            Label("Rescan Entire Library", systemImage: "arrow.triangle.2.circlepath")
                        }
                        Button {
                            showAddReceipt = true
                        } label: {
                            Label("Add Receipt Manually", systemImage: "plus")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        viewModel.viewMode = viewModel.viewMode == .grid ? .list : .grid
                    } label: {
                        Image(systemName: viewModel.viewMode.symbolName)
                    }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showFilters = true
                    } label: {
                        Image(systemName: viewModel.hasActiveFilters ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease.circle")
                    }
                }
            }
            .sheet(isPresented: $showFilters) {
                FilterSheetView(viewModel: viewModel)
            }
            .sheet(isPresented: $showAddReceipt) {
                AddReceiptSheet(importManager: importManager)
            }
            .navigationDestination(item: $selectedReceipt) { receipt in
                ReceiptDetailView(receipt: receipt)
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "receipt")
                .font(.system(size: 56))
                .foregroundStyle(.secondary)
            Text("No Receipts Yet")
                .font(.title3.bold())
            Text("Scan your photo library to automatically find receipts, or add one manually.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Button {
                Task { await importManager.scanLibrary(context: modelContext) }
            } label: {
                Label("Scan Photo Library", systemImage: "photo.stack")
                    .frame(maxWidth: 240)
            }
            .buttonStyle(.borderedProminent)
            Spacer()
            Spacer()
        }
    }

    private var noResultsState: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: "magnifyingglass")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
            Text("No receipts match your search or filters.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            if viewModel.hasActiveFilters {
                Button("Clear Filters") { viewModel.clearFilters() }
                    .buttonStyle(.bordered)
            }
            Spacer()
            Spacer()
        }
    }
}
