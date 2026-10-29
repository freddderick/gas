"""Request/response models for the HTTP API, and conversion of stored
settings JSON into analysis.AlertSettings."""

from __future__ import annotations

from datetime import time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from . import analysis


class RuleIn(BaseModel):
    enabled: bool = True
    hpa: float = Field(ge=0.5, le=50)
    hours: int = Field(ge=1, le=48)


class DirectionIn(BaseModel):
    short: RuleIn = RuleIn(enabled=True, hpa=5, hours=3)
    long: RuleIn = RuleIn(enabled=True, hpa=10, hours=24)


class AlertsIn(BaseModel):
    fall: DirectionIn = DirectionIn()
    rise: DirectionIn = DirectionIn()


class QuietHoursIn(BaseModel):
    enabled: bool = True
    start: str = "22:00"
    end: str = "07:00"

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        time.fromisoformat(value)
        return value


class LocationIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    name: str | None = Field(default=None, max_length=120)


class SettingsBody(BaseModel):
    unit: Literal["hPa", "inHg", "mmHg"] = "hPa"
    alerts: AlertsIn = AlertsIn()
    quiet_hours: QuietHoursIn = QuietHoursIn()


class InstallUpdate(BaseModel):
    """PUT /v1/installs/{id}. Every field is optional; omitted fields keep
    their stored value."""

    apns_token: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{32,200}$")
    apns_environment: Literal["production", "sandbox"] | None = None
    location: LocationIn | None = None
    timezone: str | None = None
    settings: SettingsBody | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"unknown time zone {value!r}") from exc
        return value


def to_alert_settings(body: SettingsBody) -> analysis.AlertSettings:
    def direction(d: DirectionIn) -> analysis.DirectionRules:
        return analysis.DirectionRules(
            short=analysis.Rule(d.short.enabled, d.short.hpa, d.short.hours),
            long=analysis.Rule(d.long.enabled, d.long.hpa, d.long.hours),
        )

    q = body.quiet_hours
    return analysis.AlertSettings(
        fall=direction(body.alerts.fall),
        rise=direction(body.alerts.rise),
        quiet_hours=analysis.QuietHours(q.enabled, time.fromisoformat(q.start), time.fromisoformat(q.end)),
        unit=body.unit,
    )
