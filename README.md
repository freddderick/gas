*This repo holds two independent projects: **IOU** (below) and
**[HologramCard](HologramCard/)**, a self-contained reflective hologram trading card.*

# IOU — I Owe You

An iOS app that turns the receipts already sitting in your Photos library into a searchable, filterable gallery.

## What it does

- **Scans your Photos library on-device** using Vision (`VNRecognizeTextRequest`) to find images that look like receipts — no photos or extracted text ever leave the device.
- **Builds a gallery** of detected receipts, browsable as a photo grid or a list.
- **Filters** by date range (this week / month / year / custom) and by category (groceries, dining, travel, transportation, shopping, utilities, entertainment, health, office, home, other).
- **Searches** across merchant name, notes, and the full OCR'd receipt text — including an amount (e.g. searching `24.99` finds it whether it was the total or just a line item).
- Auto-suggests a category and pulls out a total amount, purchase date, and merchant name per receipt, all editable in the detail view.
- Lets you manually tag a photo as a receipt (via `PhotosPicker`) for anything the automatic scan misses, and re-scan the library for newly added photos at any time.

## Project structure

```
IOU/
  project.yml                 # XcodeGen project definition
  IOU/
    IOUApp.swift               # App entry point, SwiftData ModelContainer
    Models/
      Receipt.swift             # SwiftData @Model
      ReceiptCategory.swift     # Category enum + keyword-based auto-categorization
    Services/
      PhotoLibraryAuthService.swift   # PHPhotoLibrary authorization
      ReceiptOCRService.swift         # Vision text recognition (UIKit/Vision dependent)
      ReceiptTextParser.swift         # Pure parsing heuristics (unit-testable, no UIKit)
      PhotoImageLoader.swift          # PHCachingImageManager-backed image loading
      ReceiptImportManager.swift      # Orchestrates library scans -> SwiftData records
    ViewModels/
      GalleryViewModel.swift    # Search / filter / sort state and logic
    Views/
      RootView.swift            # Permission gate
      GalleryView.swift         # Main screen: grid/list toggle, search, filters
      PhotoGridView.swift
      ReceiptListView.swift
      ReceiptDetailView.swift
      FilterSheetView.swift
      AddReceiptSheet.swift
      PermissionRequestView.swift
      ScanProgressView.swift
      CategoryBadge.swift
      AsyncPhotoImage.swift
    Resources/
      Assets.xcassets
  IOUTests/
    ReceiptTextParserTests.swift
    ReceiptCategoryTests.swift
    GalleryViewModelTests.swift
```

## Opening the project

This repo ships Swift source and an [XcodeGen](https://github.com/yonaskolb/XcodeGen) `project.yml` instead of a checked-in `.xcodeproj`, so the generated project file never rots or produces noisy merge conflicts.

1. Install XcodeGen (once): `brew install xcodegen`
2. From `IOU/`, generate the Xcode project:
   ```sh
   cd IOU
   xcodegen generate
   ```
3. Open `IOU.xcodeproj` in Xcode (15.0+), select the `IOU` scheme, and run on an iOS 17+ simulator or device.
4. In Xcode, set your Development Team under the `IOU` target's *Signing & Capabilities* tab to run on a physical device.

Requires **iOS 17** (uses SwiftData and the Swift Observation framework) and **Xcode 15+**.

### App icon

The asset catalog includes an empty `AppIcon` icon set placeholder — add a 1024×1024 icon image before archiving for the App Store (not required to build and run in the simulator).

## Running tests

`ReceiptTextParserTests`, `ReceiptCategoryTests`, and `GalleryViewModelTests` cover the amount/date/merchant extraction heuristics and the search/filter/sort logic with plain fixtures (no Photos library access needed). Run via `Cmd+U` in Xcode or:

```sh
xcodebuild test -project IOU.xcodeproj -scheme IOU -destination 'platform=iOS Simulator,name=iPhone 15'
```

## How receipt detection works

1. On first launch (after granting Photos access), the app scans your image library newest-first.
2. Each photo's text is recognized with Vision (`.accurate` recognition level, on-device).
3. A photo is classified as a receipt only if it contains **both** a currency-shaped amount (e.g. `$12.34`) **and** at least one receipt-ish keyword (`total`, `tax`, `subtotal`, `visa`, `thank you for`, etc.) — this keeps birthday cards with a "$20 enclosed" note or random photos with a price tag from flooding the gallery.
4. For photos classified as receipts, the app extracts a best-guess total (preferring a line containing "total" over "subtotal", falling back to the largest amount found), a purchase date (via `NSDataDetector`, sanity-checked against today), and a merchant name (first plausible text line).
5. Already-scanned photos are tracked so subsequent scans only look at new photos; "Rescan Entire Library" in the menu forces a full re-scan.

All of this metadata — plus the full recognized text — is stored locally in SwiftData; the original photo is never copied, only referenced by its Photos asset identifier.

## Privacy

- Photos access is requested via the standard `PHPhotoLibrary` permission prompt (read/write, since deleting a receipt from IOU does not delete the photo, but future export features may write back to Photos).
- All OCR and parsing happens on-device via Vision; nothing is uploaded anywhere.
