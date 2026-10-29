import PressureCore
import SwiftData
import SwiftUI

/// Simple headache and pain log (spec 4.1 item 7). Kept on the device only.
struct LogView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.modelContext) private var context
    @Query(sort: \LogEntry.date, order: .reverse) private var entries: [LogEntry]
    @State private var showingNew = false
    @State private var editing: LogEntry?

    var body: some View {
        NavigationStack {
            List {
                if entries.isEmpty {
                    ContentUnavailableView(
                        "Nothing logged yet",
                        systemImage: "list.bullet.clipboard",
                        description: Text("Log a headache or pain with one tap. Later you can export the log next to the pressure to see whether they line up.")
                    )
                }
                ForEach(entries) { entry in
                    Button { editing = entry } label: { LogRow(entry: entry) }
                        .buttonStyle(.plain)
                }
                .onDelete { offsets in
                    for index in offsets { context.delete(entries[index]) }
                }
            }
            .navigationTitle("Log")
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button { showingNew = true } label: { Label("Add entry", systemImage: "plus") }
                }
                ToolbarItem(placement: .secondaryAction) {
                    NavigationLink { ExportView() } label: { Label("Export", systemImage: "square.and.arrow.up") }
                }
            }
            .sheet(isPresented: $showingNew) { LogEntrySheet() }
            .sheet(item: $editing) { LogEntrySheet(editing: $0) }
        }
    }
}

private struct LogRow: View {
    @Environment(AppModel.self) private var model
    let entry: LogEntry

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(entry.severity)")
                .font(.title2.weight(.bold).monospacedDigit())
                .frame(width: 44, height: 44)
                .background(Color.accentColor.opacity(0.12 + Double(entry.severity) * 0.05), in: Circle())
                .accessibilityLabel("Severity \(entry.severity) of 10")
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.date.formatted(date: .abbreviated, time: .shortened)).font(.headline)
                if !entry.note.isEmpty {
                    Text(entry.note).lineLimit(2)
                }
                if let pressure = model.series.value(at: entry.date) {
                    let change = model.series.change(at: entry.date, hours: 3)
                    Text("Pressure then: \(model.unit.format(pressure))" + (change.map { ", \(model.unit.formatSignedChange($0)) over 3 h" } ?? ""))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
    }
}

/// One tap on a severity number saves the entry (with the time and optional
/// note above it). Editing an existing entry shows an explicit Save button.
struct LogEntrySheet: View {
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    var editing: LogEntry?

    @State private var date = Date.now
    @State private var note = ""
    @State private var severity: Int?

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 10), count: 5)

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    DatePicker("When", selection: $date, in: ...Date.now.addingTimeInterval(3600))
                    TextField("Note (optional)", text: $note, axis: .vertical)
                        .lineLimit(1...4)
                }
                Section {
                    LazyVGrid(columns: columns, spacing: 10) {
                        ForEach(1...10, id: \.self) { value in
                            Button {
                                severity = value
                                if editing == nil { save() }
                            } label: {
                                Text("\(value)")
                                    .font(.title3.weight(.semibold).monospacedDigit())
                                    .frame(maxWidth: .infinity, minHeight: 48)
                                    .background(
                                        severity == value ? Color.accentColor : Color.accentColor.opacity(0.12),
                                        in: RoundedRectangle(cornerRadius: 10)
                                    )
                                    .foregroundStyle(severity == value ? Color.white : Color.primary)
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("Severity \(value)")
                            .accessibilityAddTraits(severity == value ? .isSelected : [])
                        }
                    }
                    .padding(.vertical, 4)
                } header: {
                    Text("How bad, 1 to 10?")
                } footer: {
                    Text(editing == nil ? "Tap a number to save." : "1 is barely noticeable, 10 is the worst you've had.")
                }
            }
            .navigationTitle(editing == nil ? "Log headache or pain" : "Edit entry")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                if editing != nil {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Save") { save() }.disabled(severity == nil)
                    }
                }
            }
            .onAppear {
                if let editing {
                    date = editing.date
                    note = editing.note
                    severity = editing.severity
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func save() {
        guard let severity else { return }
        let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
        if let editing {
            editing.date = date
            editing.note = trimmed
            editing.severity = severity
        } else {
            context.insert(LogEntry(date: date, severity: severity, note: trimmed))
        }
        try? context.save()
        dismiss()
    }
}
