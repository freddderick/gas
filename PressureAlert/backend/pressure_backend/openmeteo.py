"""Open-Meteo forecast client (spec section 5).

Requests exactly one hourly variable, pressure_msl. surface_pressure is
deliberately not requested in v1 so it can never leak into alerts or charts.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import Settings

ATTRIBUTION = "Pressure data: Open-Meteo (open-meteo.com), CC BY 4.0"


class ForecastError(Exception):
    pass


@dataclass(frozen=True)
class Forecast:
    latitude: float
    longitude: float
    hourly: dict[int, float]  # hour-aligned unix seconds -> pressure_msl hPa


def build_params(settings: Settings, latitude: float, longitude: float) -> dict[str, str]:
    params = {
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "hourly": "pressure_msl",
        "past_days": str(settings.past_days),
        "forecast_days": str(settings.forecast_days),
        "timezone": "GMT",
        "timeformat": "unixtime",
    }
    if settings.open_meteo_api_key:
        params["apikey"] = settings.open_meteo_api_key
    return params


def parse(payload: dict) -> Forecast:
    try:
        hourly = payload["hourly"]
        times = hourly["time"]
        values = hourly["pressure_msl"]
    except (KeyError, TypeError) as exc:
        raise ForecastError(f"unexpected response shape: {exc}") from exc
    if len(times) != len(values):
        raise ForecastError("time and pressure_msl lengths differ")
    series = {int(t): float(v) for t, v in zip(times, values) if v is not None}
    if not series:
        raise ForecastError("response contained no pressure_msl values")
    return Forecast(float(payload.get("latitude", 0)), float(payload.get("longitude", 0)), series)


class OpenMeteoClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.http = http or httpx.AsyncClient(timeout=20)

    async def fetch(self, latitude: float, longitude: float) -> Forecast:
        try:
            response = await self.http.get(
                self.settings.open_meteo_url, params=build_params(self.settings, latitude, longitude)
            )
        except httpx.HTTPError as exc:
            raise ForecastError(f"request failed: {exc}") from exc
        if response.status_code != 200:
            reason = ""
            try:
                reason = response.json().get("reason", "")
            except ValueError:
                pass
            raise ForecastError(f"HTTP {response.status_code} {reason}".strip())
        return parse(response.json())

    async def aclose(self) -> None:
        await self.http.aclose()
