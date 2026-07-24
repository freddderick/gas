import SwiftUI

struct PermissionRequestView: View {
    let authService: PhotoLibraryAuthService
    var onAuthorized: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "receipt")
                .font(.system(size: 64))
                .foregroundStyle(.tint)

            VStack(spacing: 8) {
                Text("Welcome to IOU")
                    .font(.title2.bold())
                Text("IOU scans your Photos library on-device to find receipts and turns them into a searchable gallery. Nothing leaves your phone.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            if authService.isDenied {
                VStack(spacing: 12) {
                    Text("Photo access is currently denied.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Button {
                        if let url = URL(string: UIApplication.openSettingsURLString) {
                            UIApplication.shared.open(url)
                        }
                    } label: {
                        Text("Open Settings")
                            .frame(maxWidth: 280)
                    }
                    .buttonStyle(.borderedProminent)
                }
            } else {
                Button {
                    Task {
                        let status = await authService.requestAccess()
                        if status == .authorized || status == .limited {
                            onAuthorized()
                        }
                    }
                } label: {
                    Text("Allow Access to Photos")
                        .frame(maxWidth: 280)
                }
                .buttonStyle(.borderedProminent)
            }

            Spacer()
            Spacer()
        }
        .padding()
    }
}
