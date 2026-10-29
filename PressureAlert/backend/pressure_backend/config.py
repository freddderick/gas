"""Runtime configuration, read from environment variables.

Every setting has a safe development default so `pytest` and a local
`pressure-backend serve` work with no environment at all. A production
deploy sets the OPEN_METEO_API_KEY and the APNS_* values (see
deploy/env.example).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw else default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_path: str = "pressure.db"

    # Open-Meteo. With an API key the paid customer endpoint is used; without
    # one the free endpoint is used, which is for prototyping only (the free
    # tier is non-commercial).
    open_meteo_api_key: str = ""
    open_meteo_free_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_customer_url: str = "https://customer-api.open-meteo.com/v1/forecast"
    forecast_days: int = 7
    past_days: int = 2
    monthly_call_budget: int = 1_000_000

    # Locations are snapped to a grid of this many degrees so users in the
    # same city share one fetch. 0.1 degrees is about 11 km.
    grid_degrees: float = 0.1

    # Scheduling. Fetching costs API calls, evaluating does not, so the
    # evaluator runs often against the cached series and the fetcher runs
    # every 3 hours.
    fetch_interval_seconds: int = 3 * 3600
    evaluate_interval_seconds: int = 15 * 60
    # A series older than this is treated as an outage: alerts pause and the
    # app shows "Forecast unavailable, alerts paused".
    stale_after_seconds: int = 7 * 3600
    # Keep this much history per location for charts and exports.
    retain_days: int = 14
    # Installs that haven't opened the app (which re-sends settings) in this
    # long are deleted, along with their history.
    inactive_install_days: int = 90
    run_scheduler: bool = True

    # APNs token-based auth. Leave blank to run without push (alerts are still
    # evaluated and logged with status "not_configured").
    apns_team_id: str = ""
    apns_key_id: str = ""
    apns_private_key_path: str = ""
    apns_topic: str = "ca.andywood.PressureAlert"

    @property
    def open_meteo_url(self) -> str:
        return self.open_meteo_customer_url if self.open_meteo_api_key else self.open_meteo_free_url

    @property
    def apns_configured(self) -> bool:
        return bool(self.apns_team_id and self.apns_key_id and self.apns_private_key_path)


def load_settings() -> Settings:
    return Settings(
        database_path=_env("DATABASE_PATH", "pressure.db"),
        open_meteo_api_key=_env("OPEN_METEO_API_KEY"),
        forecast_days=_env_int("FORECAST_DAYS", 7),
        past_days=_env_int("PAST_DAYS", 2),
        monthly_call_budget=_env_int("OPEN_METEO_MONTHLY_BUDGET", 1_000_000),
        grid_degrees=_env_float("GRID_DEGREES", 0.1),
        fetch_interval_seconds=_env_int("FETCH_INTERVAL_SECONDS", 3 * 3600),
        evaluate_interval_seconds=_env_int("EVALUATE_INTERVAL_SECONDS", 15 * 60),
        stale_after_seconds=_env_int("STALE_AFTER_SECONDS", 7 * 3600),
        retain_days=_env_int("RETAIN_DAYS", 14),
        inactive_install_days=_env_int("INACTIVE_INSTALL_DAYS", 90),
        run_scheduler=_env_bool("RUN_SCHEDULER", True),
        apns_team_id=_env("APNS_TEAM_ID"),
        apns_key_id=_env("APNS_KEY_ID"),
        apns_private_key_path=_env("APNS_PRIVATE_KEY_PATH"),
        apns_topic=_env("APNS_TOPIC", "ca.andywood.PressureAlert"),
    )
