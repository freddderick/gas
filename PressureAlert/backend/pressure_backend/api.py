"""HTTP API for the iOS app.

There are no accounts. The app generates a random install ID and a random
secret on first launch, keeps both in the Keychain, and sends the secret as a
bearer token. The first PUT for an ID claims it; later requests must present
the same secret. The server stores only a hash of the secret.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Path, Query, Response

from . import poller
from .apns import APNsSender, PushSender
from .config import Settings, load_settings
from .db import Database
from .openmeteo import ATTRIBUTION, OpenMeteoClient
from .schemas import InstallUpdate
from .store import Install, Store, snap

log = logging.getLogger("pressure.api")


@dataclass
class Services:
    settings: Settings
    store: Store
    client: OpenMeteoClient
    sender: PushSender


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer secret")
    secret = authorization[7:].strip()
    if len(secret) < 32:
        raise HTTPException(401, "secret too short")
    return secret


def _install_id(install_id: str) -> str:
    try:
        return str(uuid.UUID(install_id))
    except ValueError:
        raise HTTPException(400, "install id must be a UUID") from None


def create_app(
    settings: Settings | None = None,
    *,
    store: Store | None = None,
    client: OpenMeteoClient | None = None,
    sender: PushSender | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    services = Services(
        settings=settings,
        store=store or Store(Database(settings.database_path)),
        client=client or OpenMeteoClient(settings),
        sender=sender or APNsSender(settings),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if settings.run_scheduler:
            task = asyncio.create_task(
                poller.run_forever(services.store, services.client, services.sender, settings)
            )
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Pressure Alert backend", version="0.1.0", lifespan=lifespan)
    app.state.services = services

    def authed(
        install_id: str = Path(...),
        authorization: str | None = Header(default=None),
    ) -> Install:
        install = services.store.get_install(_install_id(install_id))
        if install is None:
            raise HTTPException(404, "unknown install")
        if not services.store.verify_secret(install, _bearer(authorization)):
            raise HTTPException(403, "wrong secret")
        return install

    async def fetch_new_cell(cell_id: str) -> None:
        cell = services.store.get_cell(cell_id)
        if cell is not None:
            await poller.fetch_cell(services.store, services.client, settings, cell, int(time.time()))

    @app.get("/healthz")
    def healthz() -> dict:
        return {
            "ok": True,
            "active_locations": len(services.store.active_cells()),
            "open_meteo_calls_this_month": services.store.api_calls(),
            "open_meteo_monthly_budget": settings.monthly_call_budget,
            "push_configured": settings.apns_configured,
        }

    @app.put("/v1/installs/{install_id}")
    def put_install(
        body: InstallUpdate,
        background: BackgroundTasks,
        install_id: str = Path(...),
        authorization: str | None = Header(default=None),
    ) -> dict:
        install_id = _install_id(install_id)
        secret = _bearer(authorization)
        now = int(time.time())
        store = services.store
        install = store.get_install(install_id)
        if install is None:
            install = store.create_install(install_id, secret, now)
        elif not store.verify_secret(install, secret):
            raise HTTPException(403, "wrong secret")

        fields: dict = {}
        if body.apns_token is not None:
            fields["apns_token"] = body.apns_token.lower()
        if body.apns_environment is not None:
            fields["apns_environment"] = body.apns_environment
        if body.timezone is not None:
            fields["timezone"] = body.timezone
        if body.settings is not None and body.settings != install.settings:
            fields["settings_json"] = body.settings.model_dump_json()
        if body.location is not None:
            cell_id, lat, lon = snap(body.location.latitude, body.location.longitude, settings.grid_degrees)
            fields["location_name"] = body.location.name
            if cell_id != install.cell_id:
                if store.ensure_cell(cell_id, lat, lon, now) or poller.is_stale(store.get_cell(cell_id), now, settings):
                    background.add_task(fetch_new_cell, cell_id)
                fields["cell_id"] = cell_id
        store.update_install(install_id, now, **fields)
        return _install_view(store.get_install(install_id))  # type: ignore[arg-type]

    @app.get("/v1/installs/{install_id}")
    def get_install(install: Install = Depends(authed)) -> dict:
        return _install_view(install)

    @app.delete("/v1/installs/{install_id}", status_code=204)
    def delete_install(install: Install = Depends(authed)) -> Response:
        services.store.delete_install(install.id)
        return Response(status_code=204)

    @app.get("/v1/installs/{install_id}/pressure")
    def get_pressure(install: Install = Depends(authed)) -> dict:
        now = int(time.time())
        if install.cell_id is None:
            raise HTTPException(409, "no location set")
        cell = services.store.get_cell(install.cell_id)
        series = services.store.series(install.cell_id, since=now - settings.retain_days * 86400)
        if cell is None or cell.last_success_at is None:
            status = "pending" if cell is None or cell.last_error is None else "unavailable"
        else:
            status = "unavailable" if poller.is_stale(cell, now, settings) else "ok"
        return {
            "status": status,
            "alerts_paused": status != "ok",
            "message": "Forecast unavailable, alerts paused" if status == "unavailable" else None,
            "fetched_at": cell.last_success_at if cell else None,
            "grid": {"latitude": cell.latitude, "longitude": cell.longitude} if cell else None,
            "variable": "pressure_msl",
            "unit": "hPa",
            "attribution": ATTRIBUTION,
            "hourly": [{"t": ts, "msl": v} for ts, v in series.items()],
        }

    @app.get("/v1/installs/{install_id}/alerts")
    def get_alerts(install: Install = Depends(authed), limit: int = Query(100, ge=1, le=500)) -> dict:
        return {"alerts": services.store.history(install.id, limit)}

    return app


def _install_view(install: Install) -> dict:
    return {
        "id": install.id,
        "has_push_token": bool(install.apns_token),
        "apns_environment": install.apns_environment,
        "location": {"name": install.location_name, "cell": install.cell_id} if install.cell_id else None,
        "timezone": install.timezone,
        "settings": install.settings.model_dump(),
    }
