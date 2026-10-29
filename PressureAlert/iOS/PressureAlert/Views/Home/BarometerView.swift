import CoreMotion
import SwiftUI

/// Live phone barometer reading (spec 7). Station pressure only: shown on
/// its own screen, clearly labelled, never plotted on the sea-level chart and
/// never used for alerts. Only reachable on devices that have a barometer.
struct BarometerView: View {
    @State private var reader = BarometerReader()

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Phone sensor (station pressure)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    if let hPa = reader.hPa {
                        Text(String(format: "%.1f hPa", hPa))
                            .font(.system(size: 48, weight: .semibold, design: .rounded))
                            .accessibilityLabel(String(format: "%.1f hectopascals", hPa))
                    } else if let error = reader.error {
                        Text(error).foregroundStyle(.secondary)
                    } else {
                        ProgressView()
                    }
                }
                .padding(.vertical, 4)
            } footer: {
                Text("This is the actual air pressure where your phone is, not adjusted to sea level, so it won't match the forecast number. It reads lower the higher up you are and changes in lifts, cars and planes. It updates only while this screen is open, and it is never used for alerts.")
            }
        }
        .navigationTitle("Phone barometer")
        .onAppear { reader.start() }
        .onDisappear { reader.stop() }
    }
}

@MainActor
@Observable
final class BarometerReader {
    private(set) var hPa: Double?
    private(set) var error: String?
    private let altimeter = CMAltimeter()

    func start() {
        guard CMAltimeter.isRelativeAltitudeAvailable() else {
            error = "This device doesn't have a barometer."
            return
        }
        altimeter.startRelativeAltitudeUpdates(to: .main) { [weak self] data, error in
            Task { @MainActor in
                if let data {
                    // CoreMotion reports kilopascals.
                    self?.hPa = data.pressure.doubleValue * 10
                } else if error != nil {
                    self?.error = "Motion & Fitness access is off, so the sensor can't be read. You can turn it on in Settings."
                }
            }
        }
    }

    func stop() {
        altimeter.stopRelativeAltitudeUpdates()
    }
}
