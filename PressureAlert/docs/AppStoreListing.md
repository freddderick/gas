# App Store listing draft

Name is not final (spec 9.4). Check trademark and App Store availability for each candidate before choosing.

**Name candidates:** Pressure Alert · Pressure Sense · BaroAlert
**Subtitle (30 chars max):** Pressure swing alerts, up & down
*(The spec's longer idea, "Migraine and joint pain pressure alerts, in both directions.", is over the 30-character subtitle limit. Use it as the first line of the promotional text instead.)*

**Price:** $19.99 USD one-time purchase (spec 9.1). No subscription, no in-app purchases, no ads.

**Category:** Weather (primary). Do not use Medical.

**Keywords to test (100 chars max):**
`barometric pressure,migraine weather,pressure alert,arthritis weather,barometer,headache forecast`

## Promotional text

Migraine and joint pain pressure alerts, in both directions. Know when the air pressure is about to swing, before it happens.

## Description

Some people notice headaches or joint pain when the weather changes. Pressure Alert watches the barometric pressure forecast for your area and warns you when it's about to swing, whether it's falling or rising.

**Alerts that actually arrive**
• Set your own thresholds for falls and rises separately. The suggested starting point is 5 hPa in 3 hours, and 10 hPa in 24 hours.
• Alerts are sent as notifications, so they reach you even when the app is closed.
• Quiet hours keep alerts off overnight unless you turn them on.
• One swing gives you one alert, not a stream of repeats.

**Plain language, not just numbers**
Every reading comes with a trend in words ("Falling fast", "Steady", "Rising") and a short explanation of what it means.

**See swings coming**
• The next 72 hours on a chart, with now marked.
• A 7-day pattern view that highlights swing days.
• A heads-up on the home screen when the forecast shows a swing in the next 24 hours.

**A simple headache and pain log**
Log an episode with one tap and a 1-to-10 severity. Export your log, with the pressure at each entry, as a spreadsheet, plus a one-page PDF summary to bring to an appointment.

**Private by design**
No account. No sign-in. No email. No ads or tracking. Your log stays on your phone.

Pressure in hPa, inHg or mmHg. Pressure data from Open-Meteo.

This app provides weather information only. It is not a medical device and does not diagnose, treat, or prevent any condition. Talk to a clinician about headaches or joint pain.

## Screenshots (spec 9.4)

Each one needs an honest caption and no medical claims:

1. **Fall alert:** a lock screen with the notification "Pressure is falling fast: down 6 hPa in the last 3 hours, now 1008 hPa…"
2. **Rise alert:** the same for a rise.
3. **7-day pattern:** the pattern view with one or two swing days highlighted.
4. **Explainer:** the "About pressure" screen.
5. (Optional) Home screen with the 72-hour chart.

## App Review notes

- No account and no sign-in. Every feature works without one.
- Notification permission is asked during onboarding, on a screen that first explains why.
- Location is When In Use only and is used once to pick the forecast area. The user can also search for a city instead.
- Health-adjacent wording is information-only ("often linked to", "some people notice"). The disclaimer appears in onboarding and in Settings.
- To test alerts, set a 1 hPa / 1 hour threshold in Settings → Alert thresholds, with quiet hours off.

## App Privacy ("nutrition label")

- **Data linked to you:** none.
- **Data not linked to you:** coarse location (used for app functionality) and device ID (the anonymous install ID plus the push token, used for app functionality).
- **Tracking:** none.
- **Privacy policy URL:** required. Host `PrivacyPolicy.md` and paste its URL here.
