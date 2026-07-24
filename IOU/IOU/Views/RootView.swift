import SwiftUI
import SwiftData

struct RootView: View {
    @Environment(\.modelContext) private var modelContext
    @State private var authService = PhotoLibraryAuthService()
    @State private var importManager = ReceiptImportManager()
    @State private var hasStartedInitialScan = false

    var body: some View {
        Group {
            if authService.isAuthorized {
                GalleryView(importManager: importManager)
                    .task {
                        guard !hasStartedInitialScan else { return }
                        hasStartedInitialScan = true
                        await importManager.scanLibrary(context: modelContext)
                    }
            } else {
                PermissionRequestView(authService: authService) {
                    authService.refresh()
                }
            }
        }
        .onAppear { authService.refresh() }
    }
}
