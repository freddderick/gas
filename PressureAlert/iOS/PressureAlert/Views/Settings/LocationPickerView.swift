import MapKit
import SwiftUI

/// Use GPS once, or search for a city. One saved location in v1.
struct LocationPickerView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var search = LocationSearch()
    @State private var locator = LocationService()
    @State private var working = false
    @State private var error: String?
    /// Onboarding embeds this view and moves on itself after a pick.
    var onPicked: (() -> Void)?

    var body: some View {
        @Bindable var search = search
        List {
            Section {
                Button {
                    Task { await useCurrentLocation() }
                } label: {
                    Label("Use my current location", systemImage: "location.fill")
                }
                .disabled(working)
            } footer: {
                Text("Used once to find your area. Not tracked in the background.")
            }
            if let error {
                Section { Text(error).foregroundStyle(.orange) }
            }
            Section("Or search") {
                TextField("City or town", text: $search.query)
                    .textInputAutocapitalization(.words)
                    .autocorrectionDisabled()
                ForEach(search.results, id: \.self) { result in
                    Button {
                        Task { await pick(result) }
                    } label: {
                        VStack(alignment: .leading) {
                            Text(result.title).foregroundStyle(.primary)
                            if !result.subtitle.isEmpty {
                                Text(result.subtitle).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    .disabled(working)
                }
            }
            if let current = model.location {
                Section("Saved") {
                    Label(current.name, systemImage: "mappin.and.ellipse")
                }
            }
        }
        .overlay { if working { ProgressView() } }
        .navigationTitle("Location")
    }

    private func useCurrentLocation() async {
        working = true
        defer { working = false }
        do {
            await save(try await locator.currentLocation())
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func pick(_ completion: MKLocalSearchCompletion) async {
        working = true
        defer { working = false }
        do {
            await save(try await search.resolve(completion))
        } catch {
            self.error = "Couldn't find that place. Try another search."
        }
    }

    private func save(_ location: SavedLocation) async {
        error = nil
        await model.setLocation(location)
        if let onPicked {
            onPicked()
        } else {
            dismiss()
        }
    }
}
