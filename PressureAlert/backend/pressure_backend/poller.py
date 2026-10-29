"""The two scheduled jobs (spec section 6.1-6.2).

fetch_all: once per deduplicated cell, pull pressure_msl from Open-Meteo and
merge it into the stored series. This is the only job that costs API calls,
so it runs every 3 hours.

evaluate_all: for every install, run the alert state machine over the hours
completed since its last evaluation, and push any crossings. It reads only
the stored series, so it can run every few minutes for free.
"""

from __future__ import annotations

import asyncio
import logging
import time
from zoneinfo import ZoneInfo

from . import analysis
from .apns import PushMessage, PushSender
from .config import Settings
from .openmeteo import ForecastError, OpenMeteoClient
from .schemas import to_alert_settings
from .store import Cell, Store

log = logging.getLogger("pressure.poller")

FETCH_CONCURRENCY = 8


def is_stale(cell: Cell | None, now: int, settings: Settings) -> bool:
    return cell is None or cell.last_success_at is None or now - cell.last_success_at > settings.stale_after_seconds


async def fetch_cell(store: Store, client: OpenMeteoClient, settings: Settings, cell: Cell, now: int) -> bool:
    calls = store.count_api_call(now)
    for pct in (80, 90, 100):
        if calls == settings.monthly_call_budget * pct // 100:
            log.warning("Open-Meteo usage at %d%% of monthly budget (%d calls)", pct, calls)
    try:
        forecast = await client.fetch(cell.latitude, cell.longitude)
    except ForecastError as exc:
        log.error("fetch failed for cell %s: %s", cell.id, exc)
        store.record_fetch_error(cell.id, str(exc), now)
        return False
    store.save_series(cell.id, forecast.hourly, now, settings.retain_days)
    return True


async def fetch_all(store: Store, client: OpenMeteoClient, settings: Settings, now: int | None = None) -> int:
    now = int(now or time.time())
    removed = store.delete_inactive_installs(now - settings.inactive_install_days * 86400)
    if removed:
        log.info("deleted %d inactive installs", removed)
    cells = store.active_cells()
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def one(cell: Cell) -> bool:
        async with semaphore:
            return await fetch_cell(store, client, settings, cell, now)

    results = await asyncio.gather(*(one(c) for c in cells))
    ok = sum(results)
    log.info("fetched %d/%d cells", ok, len(cells))
    return ok


async def evaluate_all(store: Store, sender: PushSender, settings: Settings, now: int | None = None) -> int:
    """Returns the number of notifications sent."""
    now = int(now or time.time())
    sent = 0
    for cell in store.active_cells():
        if is_stale(cell, now, settings):
            # Outage: alerts pause visibly rather than firing on old data.
            continue
        series = store.series(cell.id, since=now - 2 * 86400)
        for install in store.installs_in_cell(cell.id):
            sent += await evaluate_install(store, sender, install, series, now)
    return sent


async def evaluate_install(store: Store, sender: PushSender, install, series, now: int) -> int:
    states = store.alert_states(install.id)
    decisions, last = analysis.evaluate(
        series,
        now,
        install.last_evaluated_ts,
        to_alert_settings(install.settings),
        states,
        ZoneInfo(install.timezone),
    )
    sent = 0
    for decision in decisions:
        if decision.quiet:
            status = "quiet_hours"
        elif not install.apns_token:
            status = "no_token"
        else:
            status = await sender.send(
                PushMessage(install.apns_token, install.apns_environment, decision.title, decision.body)
            )
            if status == "unregistered":
                store.clear_apns_token(install.id)
            sent += status == "sent"
        store.add_history(install.id, decision, status, now)
    store.save_alert_states(install.id, states)
    store.set_last_evaluated(install.id, last)
    return sent


async def run_forever(store: Store, client: OpenMeteoClient, sender: PushSender, settings: Settings) -> None:
    # Both loops evaluate; never let them interleave on the same install.
    evaluating = asyncio.Lock()

    async def fetch_loop() -> None:
        while True:
            try:
                await fetch_all(store, client, settings)
                async with evaluating:
                    await evaluate_all(store, sender, settings)
            except Exception:  # keep the loop alive; the next cycle retries
                log.exception("fetch cycle failed")
            await asyncio.sleep(settings.fetch_interval_seconds)

    async def evaluate_loop() -> None:
        while True:
            await asyncio.sleep(settings.evaluate_interval_seconds)
            try:
                async with evaluating:
                    await evaluate_all(store, sender, settings)
            except Exception:
                log.exception("evaluate cycle failed")

    await asyncio.gather(fetch_loop(), evaluate_loop())
