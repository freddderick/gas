import PressureCore
import SwiftUI

/// Separate fall and rise thresholds, each with a size and a window
/// (spec 4.1 item 5).
struct AlertSettingsView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        Form {
            DirectionSection(direction: .fall, rules: $model.settings.alerts.fall, unit: model.unit)
            DirectionSection(direction: .rise, rules: $model.settings.alerts.rise, unit: model.unit)
            Section {
                Button("Reset to suggested defaults") {
                    model.settings.alerts = AlertRuleSet()
                }
            } footer: {
                Text("Suggested: 5 hPa in 3 hours, and 10 hPa in 24 hours, in both directions. After an alert, the same direction stays quiet until pressure recovers by 2 hPa or swings the other way, so one swing never alerts twice.")
            }
        }
        .navigationTitle("Alert thresholds")
    }
}

private struct DirectionSection: View {
    let direction: PressureDirection
    @Binding var rules: DirectionRules
    let unit: PressureUnit

    var body: some View {
        Section {
            RuleEditor(title: "Fast change", rule: $rules.short, unit: unit, hourChoices: [1, 2, 3, 4, 6])
            RuleEditor(title: "Over a day", rule: $rules.long, unit: unit, hourChoices: [12, 18, 24, 36, 48])
        } header: {
            Label(
                direction == .fall ? "When pressure falls" : "When pressure rises",
                systemImage: direction == .fall ? "arrow.down" : "arrow.up"
            )
            .foregroundStyle(Color.forDirection(direction))
        } footer: {
            if let example = example {
                Text("Example alert: \u{201C}\(example)\u{201D}")
            }
        }
    }

    private var example: String? {
        guard let rule = rules.enabledRules.first else { return nil }
        let change = direction == .fall ? -(rule.hpa + 1) : rule.hpa + 1
        let crossing = Crossing(direction: direction, time: .now, pressure: direction == .fall ? 1004 : 1024, change: change, rule: rule)
        return AlertText.body(for: crossing, unit: unit)
    }
}

private struct RuleEditor: View {
    let title: String
    @Binding var rule: AlertRule
    let unit: PressureUnit
    let hourChoices: [Int]

    var body: some View {
        Toggle(title, isOn: $rule.enabled)
        if rule.enabled {
            Stepper(value: $rule.hpa, in: 1...30, step: 1) {
                LabeledContent("Change of at least", value: unit.formatChange(rule.hpa))
            }
            .accessibilityValue(unit.formatChange(rule.hpa))
            Picker("Within", selection: $rule.hours) {
                ForEach(choices, id: \.self) { hours in
                    Text(hours == 1 ? "1 hour" : "\(hours) hours").tag(hours)
                }
            }
        }
    }

    /// Always include the stored value so the picker never shows blank.
    private var choices: [Int] {
        Array(Set(hourChoices + [rule.hours])).sorted()
    }
}
