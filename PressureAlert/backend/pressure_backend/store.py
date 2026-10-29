"""Data access on top of db.Database."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from . import analysis
from .db import Database
from .schemas import SettingsBody


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def snap(latitude: float, longitude: float, grid: float) -> tuple[str, float, float]:
    """Snap to the grid cell centre. Users in the same city share a cell, and
    the server never stores exact device coordinates."""
    lat = round(round(latitude / grid) * grid, 4)
    lon = round(round(longitude / grid) * grid, 4)
    if lon <= -180:
        lon += 360
    return f"{lat:.4f},{lon:.4f}", lat, lon


@dataclass
class Install:
    id: str
    secret_hash: str
    apns_token: str | None
    apns_environment: str
    cell_id: str | None
    location_name: str | None
    timezone: str
    settings: SettingsBody
    last_evaluated_ts: int | None


@dataclass
class Cell:
    id: str
    latitude: float
    longitude: float
    last_fetch_at: int | None
    last_success_at: int | None
    last_error: str | None


def _install(row) -> Install:
    return Install(
        id=row["id"],
        secret_hash=row["secret_hash"],
        apns_token=row["apns_token"],
        apns_environment=row["apns_environment"],
        cell_id=row["cell_id"],
        location_name=row["location_name"],
        timezone=row["timezone"],
        settings=SettingsBody.model_validate_json(row["settings_json"]),
        last_evaluated_ts=row["last_evaluated_ts"],
    )


def _cell(row) -> Cell:
    return Cell(
        row["id"], row["latitude"], row["longitude"], row["last_fetch_at"], row["last_success_at"], row["last_error"]
    )


class Store:
    def __init__(self, db: Database) -> None:
        self.db = db

    # Installs -----------------------------------------------------------------

    def get_install(self, install_id: str) -> Install | None:
        row = self.db.query_one("SELECT * FROM installs WHERE id = ?", (install_id,))
        return _install(row) if row else None

    def verify_secret(self, install: Install, secret: str) -> bool:
        return hmac.compare_digest(install.secret_hash, hash_secret(secret))

    def create_install(self, install_id: str, secret: str, now: int) -> Install:
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO installs (id, secret_hash, settings_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (install_id, hash_secret(secret), SettingsBody().model_dump_json(), now, now),
            )
        return self.get_install(install_id)  # type: ignore[return-value]

    def update_install(self, install_id: str, now: int, **fields) -> None:
        """Updates the given columns. Moving to another cell resets the dedup
        state, since the old crossing belongs to another place. Editing
        thresholds does not, so a tweak never re-sends the same crossing."""
        if not fields:
            return
        reset = "cell_id" in fields
        if reset:
            fields["last_evaluated_ts"] = None
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self.db.tx() as c:
            c.execute(f"UPDATE installs SET {cols}, updated_at = ? WHERE id = ?", (*fields.values(), now, install_id))
            if reset:
                c.execute("DELETE FROM alert_state WHERE install_id = ?", (install_id,))
        self.gc_cells()

    def delete_install(self, install_id: str) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM installs WHERE id = ?", (install_id,))
        self.gc_cells()

    def delete_inactive_installs(self, older_than: int) -> int:
        with self.db.tx() as c:
            deleted = c.execute("DELETE FROM installs WHERE updated_at < ?", (older_than,)).rowcount
        self.gc_cells()
        return deleted

    def installs_in_cell(self, cell_id: str) -> list[Install]:
        return [_install(r) for r in self.db.query("SELECT * FROM installs WHERE cell_id = ?", (cell_id,))]

    def clear_apns_token(self, install_id: str) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE installs SET apns_token = NULL WHERE id = ?", (install_id,))

    def set_last_evaluated(self, install_id: str, ts: int | None) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE installs SET last_evaluated_ts = ? WHERE id = ?", (ts, install_id))

    # Cells and series ---------------------------------------------------------

    def ensure_cell(self, cell_id: str, lat: float, lon: float, now: int) -> bool:
        """Returns True if the cell is new (and so has no data yet)."""
        with self.db.tx() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO cells (id, latitude, longitude, created_at) VALUES (?, ?, ?, ?)",
                (cell_id, lat, lon, now),
            )
            return cur.rowcount == 1

    def get_cell(self, cell_id: str) -> Cell | None:
        row = self.db.query_one("SELECT * FROM cells WHERE id = ?", (cell_id,))
        return _cell(row) if row else None

    def active_cells(self) -> list[Cell]:
        """Deduplicated: one row per cell that at least one install uses."""
        rows = self.db.query(
            "SELECT * FROM cells WHERE id IN (SELECT DISTINCT cell_id FROM installs WHERE cell_id IS NOT NULL)"
        )
        return [_cell(r) for r in rows]

    def gc_cells(self) -> None:
        with self.db.tx() as c:
            c.execute("DELETE FROM cells WHERE id NOT IN (SELECT DISTINCT cell_id FROM installs WHERE cell_id IS NOT NULL)")

    def save_series(self, cell_id: str, hourly: dict[int, float], now: int, retain_days: int) -> None:
        """Newer fetches overwrite older values hour by hour; the series only
        ever holds pressure_msl from the one provider."""
        with self.db.tx() as c:
            c.executemany(
                "INSERT INTO samples (cell_id, ts, pressure_msl) VALUES (?, ?, ?) "
                "ON CONFLICT(cell_id, ts) DO UPDATE SET pressure_msl = excluded.pressure_msl",
                [(cell_id, ts, round(v, 2)) for ts, v in hourly.items()],
            )
            c.execute("DELETE FROM samples WHERE cell_id = ? AND ts < ?", (cell_id, now - retain_days * 86400))
            c.execute(
                "UPDATE cells SET last_fetch_at = ?, last_success_at = ?, last_error = NULL WHERE id = ?",
                (now, now, cell_id),
            )

    def record_fetch_error(self, cell_id: str, error: str, now: int) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE cells SET last_fetch_at = ?, last_error = ? WHERE id = ?", (now, error[:500], cell_id))

    def series(self, cell_id: str, since: int | None = None) -> dict[int, float]:
        rows = self.db.query(
            "SELECT ts, pressure_msl FROM samples WHERE cell_id = ? AND ts >= ? ORDER BY ts",
            (cell_id, since if since is not None else 0),
        )
        return {r["ts"]: r["pressure_msl"] for r in rows}

    # Alert state and history --------------------------------------------------

    def alert_states(self, install_id: str) -> dict[analysis.Direction, analysis.DirectionState]:
        states = {d: analysis.DirectionState() for d in analysis.DIRECTIONS}
        for r in self.db.query("SELECT * FROM alert_state WHERE install_id = ?", (install_id,)):
            states[r["direction"]] = analysis.DirectionState(r["alerted_level"], r["alerted_ts"])
        return states

    def save_alert_states(self, install_id: str, states: dict[analysis.Direction, analysis.DirectionState]) -> None:
        with self.db.tx() as c:
            c.executemany(
                "INSERT INTO alert_state (install_id, direction, alerted_level, alerted_ts) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(install_id, direction) DO UPDATE SET "
                "alerted_level = excluded.alerted_level, alerted_ts = excluded.alerted_ts",
                [(install_id, d, s.alerted_level, s.alerted_ts) for d, s in states.items()],
            )

    def add_history(self, install_id: str, decision: analysis.AlertDecision, status: str, now: int) -> None:
        c_ = decision.crossing
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO alert_history (install_id, created_at, ts, direction, window_hours, threshold_hpa, "
                "change_hpa, pressure_hpa, status, title, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    install_id, now, c_.ts, c_.direction, c_.rule.hours, c_.rule.hpa,
                    round(c_.change, 2), round(c_.pressure, 2), status, decision.title, decision.body,
                ),
            )

    def history(self, install_id: str, limit: int = 100) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM alert_history WHERE install_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (install_id, limit),
        )
        return [
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "ts": r["ts"],
                "direction": r["direction"],
                "window_hours": r["window_hours"],
                "threshold_hpa": r["threshold_hpa"],
                "change_hpa": r["change_hpa"],
                "pressure_hpa": r["pressure_hpa"],
                "status": r["status"],
                "title": r["title"],
                "body": r["body"],
            }
            for r in rows
        ]

    # API budget ---------------------------------------------------------------

    def count_api_call(self, now: int) -> int:
        month = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m")
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO api_usage (month, calls) VALUES (?, 1) "
                "ON CONFLICT(month) DO UPDATE SET calls = calls + 1",
                (month,),
            )
            return c.execute("SELECT calls FROM api_usage WHERE month = ?", (month,)).fetchone()["calls"]

    def api_calls(self, now: int | None = None) -> int:
        month = datetime.fromtimestamp(now or time.time(), timezone.utc).strftime("%Y-%m")
        row = self.db.query_one("SELECT calls FROM api_usage WHERE month = ?", (month,))
        return row["calls"] if row else 0
