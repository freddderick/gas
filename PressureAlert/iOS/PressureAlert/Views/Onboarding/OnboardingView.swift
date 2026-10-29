import SwiftUI

/// Three screens (spec 4.1 item 10): location, notifications, and "not
/// medical advice". Each permission is asked with its reason on screen first,
/// never cold on launch. No account step.
struct OnboardingView: View {
    @Environment(AppModel.self) private var model
    @State private var step = Step.location

    enum Step: Int, CaseIterable { case location, notifications, disclaimer }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ProgressView(value: Double(step.rawValue + 1), total: Double(Step.allCases.count))
                    .padding(.horizontal)
                    .accessibilityLabel("Step \(step.rawValue + 1) of \(Step.allCases.count)")
                switch step {
                case .location:
                    LocationStep { step = .notifications }
                case .notifications:
                    NotificationStep { step = .disclaimer }
                case .disclaimer:
                    DisclaimerStep {
                        model.hasCompletedOnboarding = true
                    }
                }
            }
            .animation(.default, value: step)
        }
    }
}

private struct StepHeader: View {
    let icon: String
    let title: String
    let text: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 52))
                .foregroundStyle(Color.accentColor)
                .accessibilityHidden(true)
            Text(title)
                .font(.title.bold())
                .multilineTextAlignment(.center)
            Text(text)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 24)
        .padding(.top, 24)
    }
}

private struct LocationStep: View {
    @Environment(AppModel.self) private var model
    let next: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            StepHeader(
                icon: "location.circle",
                title: "Where should we watch the pressure?",
                text: "Pressure Alert warns you when air pressure is about to swing, up or down. It needs one location to know which forecast to watch. Use your location once, or search for your city."
            )
            LocationPickerView(onPicked: next)
                .scrollContentBackground(.hidden)
            if model.location != nil {
                Button("Continue", action: next)
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .padding()
            }
        }
    }
}

private struct NotificationStep: View {
    @Environment(AppModel.self) private var model
    let next: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            StepHeader(
                icon: "bell.badge",
                title: "Get alerts, even when the app is closed",
                text: "Alerts are the point of this app. When pressure falls or rises past your threshold (5 hPa in 3 hours to start), we send a notification. Quiet hours keep them off overnight unless you choose otherwise."
            )
            Spacer()
            VStack(spacing: 12) {
                Button {
                    Task {
                        await model.requestNotifications()
                        next()
                    }
                } label: {
                    Text("Allow notifications").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                Button("Not now", action: next)
            }
            .padding()
        }
    }
}

private struct DisclaimerStep: View {
    let done: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                StepHeader(
                    icon: "heart.text.square",
                    title: "Weather information, not medical advice",
                    text: "Some people notice headaches or joint pain when pressure swings. Pressure is one trigger among many, and this app can't tell you why you feel the way you do."
                )
                Text(Copy.disclaimer)
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
                    .padding(.horizontal)
                Button(action: done) {
                    Text("I understand").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .padding()
            }
        }
    }
}
