# Pressure Alert

An iOS app that warns people who get migraines or arthritis pain when barometric pressure is about to swing, in either direction, and explains each reading in plain language. It was built from `Barometric_pressure_app_spec.md` (Oct 26, 2026).

It has no account, no subscription and no ads. Alerts are pushed from a small backend, so they fire with the app closed.

```
PressureAlert/
  backend/            Python (FastAPI + SQLite): Open-Meteo poller, alert math, APNs sender
  iOS/
    project.yml       XcodeGen project (SwiftUI, iOS 17, Swift Charts, SwiftData)
    PressureCore/     Swift package: series, trend, pattern, swing detection, units, CSV. No UIKit.
    PressureAlert/    The app
    PressureAlertTests/
  docs/
    AppStoreListing.md   Description (with the required disclaimer), keywords, screenshots, review notes
    PrivacyPolicy.md     Draft policy; fill in the bracketed placeholders
```

## How it works

```
 iPhone app ──PUT settings, token, location──▶ backend ──every 3 h, once per ~10 km cell──▶ Open-Meteo
     ▲          GET series + alert history       │      (pressure_msl only)
     └───────────────── APNs push ◀──────────────┘  evaluates every 15 min against the stored series
```

- **One variable (spec 5.3).** Only `pressure_msl` is requested and stored. `surface_pressure` isn't fetched in v1, so it can't leak into alerts or charts. The phone barometer is shown on its own screen, labelled "Phone sensor (station pressure)", and is never charted with the forecast or used for alerts.
- **Cost levers (spec 6.2).** Locations are snapped to a 0.1° grid, so everyone in a city shares one fetch, and fetching happens every 3 hours. Evaluation runs every 15 minutes, but it reads only the stored hourly series, so it costs no API calls and still catches a crossing within the hour it happens. `/healthz` reports calls this month against the budget, and the server logs a warning at 80%, 90% and 100%.
- **Alert math (spec 6.3)** is in `backend/pressure_backend/analysis.py`:
  - Change = pressure now − pressure N hours ago.
  - Fall and rise each have a short rule (default 5 hPa in 3 h) and a long rule (default 10 hPa in 24 h). The user can change the size and window of each rule and turn it on or off.
  - After a direction alerts, it stays quiet until pressure recovers 2 hPa from the alerted level, or until the opposite direction alerts.
  - Quiet hours are evaluated in the location's time zone. An alert during quiet hours is logged in the history as "not sent: quiet hours" and isn't re-sent in the morning.
  - After downtime, the evaluator catches up at most 6 hours, so it never sends a stale alert.
- **Outage handling.** If Open-Meteo fails or the series is over 7 h old, alerts pause. The API returns `"Forecast unavailable, alerts paused"`, and the app shows that message in a banner. There is no fallback provider, by design (spec 6.4).
- **No account.** The app creates a random UUID and a 256-bit secret, kept in the Keychain. The first PUT claims the ID, and the server stores only a SHA-256 hash of the secret. Exact coordinates never leave the server's request handler; only the snapped cell is stored. Installs that don't open the app for 90 days are deleted.
- **Alert wording** is identical in `analysis.alert_text` (Python) and `AlertText` (Swift), for example: *"Pressure is falling fast: down 6 hPa in the last 3 hours, now 1008 hPa. Your alert is set for 5 hPa in 3 hours. A swing like this is often linked to headaches."* Both have tests.

## Backend

```sh
cd PressureAlert/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                                   # 32 tests: alert math, API, poller, APNs signing
RUN_SCHEDULER=true pressure-backend serve --port 8000
```

With no environment set, it uses `./pressure.db`, the **free** Open-Meteo endpoint, and no push (alerts are logged with status `not_configured`). For production, copy `deploy/env.example` to `/etc/pressure-alert/env` and set:

- `OPEN_METEO_API_KEY`: switches to `customer-api.open-meteo.com` (Standard plan). Don't ship a commercial app on the free tier.
- `APNS_TEAM_ID`, `APNS_KEY_ID`, `APNS_PRIVATE_KEY_PATH`: an APNs auth key (.p8) from Apple Developer → Keys.
- `APNS_TOPIC`: the app's bundle ID (default `ca.andywood.PressureAlert`).

The deploy files assume one small VPS: `deploy/pressure-alert.service` (systemd) and `deploy/Caddyfile` (automatic TLS). The app is one process, with the scheduler running inside the API server. One-off commands are `pressure-backend fetch-once` and `pressure-backend evaluate-once`.

API (bearer secret on every call):

| Method | Path | |
|---|---|---|
| PUT | `/v1/installs/{uuid}` | Create or update: `apns_token`, `apns_environment`, `location`, `timezone`, `settings` |
| GET | `/v1/installs/{uuid}/pressure` | `status` (`ok`, `pending` or `unavailable`), `message`, `fetched_at`, hourly `{t, msl}` for up to 14 days back plus 7 days ahead, `attribution` |
| GET | `/v1/installs/{uuid}/alerts` | Alert history, newest first |
| DELETE | `/v1/installs/{uuid}` | Delete everything for this install |
| GET | `/healthz` | Active locations, API calls this month, whether push is configured |

## iOS app

1. `brew install xcodegen`, then `cd PressureAlert/iOS && xcodegen generate`, then open `PressureAlert.xcodeproj` (Xcode 15+).
2. Set your team under Signing & Capabilities. Push Notifications is already in the entitlements file.
3. **Backend URL:** set the `PA_BACKEND_URL` build setting, e.g. `https://api.example.com` (the project sets it to blank). If it's blank, the app runs in **prototype mode**. It reads Open-Meteo's free endpoint directly, so you can try the UI in the simulator, but there are no push alerts or alert history, and a banner says so. Never ship in prototype mode.
4. Debug builds register with `apns_environment = sandbox`, and Release/TestFlight builds with `production`.
5. Tests: `cd iOS/PressureCore && swift test` runs the core logic tests (series, trend labels, swing days, forecast swing, units, CSV, alert text). The app test target covers JSON coding with the backend.

Screens: onboarding (location, then notifications, then "not medical advice"), Now (current pressure, trend arrow and words, 72-hour chart with now marked, next 24-hour swing warning, log button, links), pressure detail (deep-link target `pressurealert://pressure`, the 3, 6 and 24 h changes), 7-day pattern (high, low and net change, swing days highlighted, tap for hourly), log (one tap on a severity number saves), alert history, explainer, settings (units, separate fall and rise thresholds with an example alert, quiet hours, location, notification status, export, delete server data, privacy, disclaimer, attribution), export (pressure CSV, log CSV with pressure at each entry, one-page PDF), and the phone barometer (only on devices that have one).

Accessibility: falls and rises always show an arrow and a word, not just a colour. Charts have VoiceOver audio-graph descriptors, text uses Dynamic Type, and the colours have dark-mode variants.

## Acceptance criteria (spec 14)

| Criterion | Where |
|---|---|
| Current sea-level pressure with trend arrow and plain-language label | `CurrentPressureCard`, `PressureTrend` |
| 72-hour chart and 7-day pattern from `pressure_msl` only | `PressureChart`, `PatternView`, `PressureSeries` (holds msl only); backend requests only `pressure_msl` (tested) |
| Separate fall and rise thresholds; push on a crossing in either direction with the app closed | `AlertSettingsView`; `analysis.py` + `poller.py` + `apns.py` (tested) |
| No duplicate alerts; quiet hours respected | 2 hPa recovery and opposite-direction re-arm; quiet hours in local time (tested) |
| Works with no account, offline from cache | Keychain install identity; `DiskCache` |
| Log saves; CSV export works | `LogView`, `CSVExport` (tested), `ExportView` |
| Open-Meteo attribution; disclaimer in onboarding, Settings and the App Store draft | `Copy`, `DisclaimerStep`, `SettingsView`, `docs/AppStoreListing.md` |
| No-barometer devices handled; sensor labelled station pressure and never used for alerts | `BarometerView` is only linked when `CMAltimeter.isRelativeAltitudeAvailable()` |

## Not verified in this build, and still to do

- **The Swift code has not been compiled.** It was written in a Linux container with no Swift toolchain or Xcode. Expect a few compile fixes on the first Xcode build. The Python backend is fully tested (32 passing tests) and was smoke-tested with uvicorn.
- **No live call to Open-Meteo has been made.** The build environment's network blocks it, so parsing is tested against the documented response shape (`hourly.time` as unixtime and `hourly.pressure_msl`). Run `pressure-backend fetch-once` once against the real endpoint.
- **No real push has been sent.** APNs request signing and the payload are tested with a generated key. Sending a real push needs your .p8 key and a device.
- **App icon:** the `AppIcon` set is empty. Add a 1024×1024 image before archiving.
- **Spec section 12 validation steps are yours to do:** confirm the Open-Meteo price at checkout, run the Visual Crossing check, read the reviews, check names and trademarks, and run the one-week TestFlight alert trial.
- **v2 (spec 4.2), deliberately not built:** multiple locations, widgets and Watch, a 14-day pattern (`FORECAST_DAYS=14` on the backend and `days(14)` in the app would enable it), a surface pressure line, a correlation view, and an iPad layout.
