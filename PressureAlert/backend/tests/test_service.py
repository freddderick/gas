"""End-to-end tests: HTTP API + poller + APNs sender, with Open-Meteo and
APNs replaced by httpx mock transports."""

import asyncio
import json
import time
import uuid
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from pressure_backend import poller
from pressure_backend.api import create_app
from pressure_backend.apns import APNsSender, PushMessage
from pressure_backend.config import Settings
from pressure_backend.db import Database
from pressure_backend.openmeteo import OpenMeteoClient, build_params
from pressure_backend.store import Store, snap

H = 3600
SECRET = "s" * 40


class FakeOpenMeteo:
    """Serves a configurable pressure_msl series and records requests."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.values: dict[int, float] = {}
        self.fail = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            return httpx.Response(503, json={"error": True, "reason": "maintenance"})
        times = sorted(self.values)
        return httpx.Response(
            200,
            json={
                "latitude": float(request.url.params["latitude"]),
                "longitude": float(request.url.params["longitude"]),
                "hourly": {"time": times, "pressure_msl": [self.values[t] for t in times]},
            },
        )


class RecordingSender:
    def __init__(self, status: str = "sent") -> None:
        self.messages: list[PushMessage] = []
        self.status = status

    async def send(self, message: PushMessage):
        self.messages.append(message)
        return self.status


@pytest.fixture
def env():
    settings = Settings(database_path=":memory:", run_scheduler=False)
    store = Store(Database(":memory:"))
    meteo = FakeOpenMeteo()
    client = OpenMeteoClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(meteo.handler)))
    sender = RecordingSender()
    app = create_app(settings, store=store, client=client, sender=sender)
    with TestClient(app) as http:
        yield http, store, meteo, sender, settings, client


def auth(secret: str = SECRET) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def register(http, install_id: str, **body):
    payload = {
        "apns_token": "ab" * 32,
        "apns_environment": "sandbox",
        "location": {"latitude": 43.6532, "longitude": -79.3832, "name": "Toronto"},
        "timezone": "UTC",
        "settings": {"quiet_hours": {"enabled": False}},
    }
    payload.update(body)
    return http.put(f"/v1/installs/{install_id}", json=payload, headers=auth())


def now_hour() -> int:
    return int(time.time()) // H * H


def test_request_asks_for_pressure_msl_only():
    params = build_params(Settings(), 43.65, -79.38)
    assert params["hourly"] == "pressure_msl"
    assert "surface_pressure" not in json.dumps(params)
    paid = build_params(Settings(open_meteo_api_key="k"), 1, 2)
    assert paid["apikey"] == "k"
    assert Settings(open_meteo_api_key="k").open_meteo_url.startswith("https://customer-api.open-meteo.com")


def test_snap_dedupes_nearby_locations():
    a = snap(43.6532, -79.3832, 0.1)
    b = snap(43.6711, -79.4011, 0.1)
    assert a[0] == b[0] == "43.7000,-79.4000"


def test_register_claims_id_and_rejects_other_secrets(env):
    http, store, meteo, *_ = env
    iid = str(uuid.uuid4())
    meteo.values = {now_hour() - i * H: 1012.0 for i in range(30)}
    r = register(http, iid)
    assert r.status_code == 200
    assert r.json()["location"]["name"] == "Toronto"
    assert r.json()["has_push_token"] is True

    assert http.get(f"/v1/installs/{iid}", headers=auth("x" * 40)).status_code == 403
    assert http.put(f"/v1/installs/{iid}", json={}, headers=auth("x" * 40)).status_code == 403
    assert http.get(f"/v1/installs/{iid}").status_code == 401
    assert http.get(f"/v1/installs/not-a-uuid", headers=auth()).status_code == 400

    # The new cell was fetched straight away in the background.
    assert len(meteo.requests) == 1
    pressure = http.get(f"/v1/installs/{iid}/pressure", headers=auth()).json()
    assert pressure["status"] == "ok" and pressure["variable"] == "pressure_msl"
    assert "Open-Meteo" in pressure["attribution"]
    assert len(pressure["hourly"]) == 30


def test_exact_location_is_not_stored(env):
    http, store, *_ = env
    iid = str(uuid.uuid4())
    register(http, iid)
    rows = store.db.query("SELECT latitude, longitude FROM cells")
    assert [(r["latitude"], r["longitude"]) for r in rows] == [(43.7, -79.4)]


def test_two_installs_in_one_city_share_one_fetch(env):
    http, store, meteo, sender, settings, client = env
    meteo.values = {now_hour() - i * H: 1012.0 for i in range(30)}
    register(http, str(uuid.uuid4()))
    register(http, str(uuid.uuid4()), location={"latitude": 43.67, "longitude": -79.40})
    meteo.requests.clear()
    asyncio.run(poller.fetch_all(store, client, settings))
    assert len(meteo.requests) == 1
    assert store.api_calls() >= 1


def test_fall_alert_is_pushed_once_and_logged(env):
    http, store, meteo, sender, settings, client = env
    t = now_hour()
    meteo.values = {t - i * H: 1012.0 for i in range(4, 30)}
    meteo.values.update({t - 3 * H: 1012.0, t - 2 * H: 1010.0, t - H: 1008.0, t: 1006.0, t + H: 1005.0})
    iid = str(uuid.uuid4())
    register(http, iid)

    assert asyncio.run(poller.evaluate_all(store, sender, settings)) == 1
    msg = sender.messages[0]
    assert msg.title == "Pressure falling fast"
    assert "down 6 hPa in the last 3 hours, now 1006 hPa" in msg.body
    assert msg.environment == "sandbox" and msg.deep_link == "pressurealert://pressure"

    # Same crossing, next evaluation and next fetch: no duplicate.
    asyncio.run(poller.fetch_all(store, client, settings))
    assert asyncio.run(poller.evaluate_all(store, sender, settings)) == 0

    alerts = http.get(f"/v1/installs/{iid}/alerts", headers=auth()).json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["direction"] == "fall" and alerts[0]["status"] == "sent"
    assert alerts[0]["change_hpa"] == -6 and alerts[0]["threshold_hpa"] == 5 and alerts[0]["window_hours"] == 3


def test_rise_alert_in_inhg(env):
    http, store, meteo, sender, settings, _ = env
    t = now_hour()
    meteo.values = {t - i * H: 1000.0 for i in range(3, 30)}
    meteo.values.update({t - 2 * H: 1002.0, t - H: 1004.0, t: 1006.0})
    register(http, str(uuid.uuid4()), settings={"unit": "inHg", "quiet_hours": {"enabled": False}})
    asyncio.run(poller.evaluate_all(store, sender, settings))
    assert sender.messages[0].title == "Pressure rising fast"
    assert "inHg" in sender.messages[0].body


def test_quiet_hours_suppress_push_but_log(env):
    http, store, meteo, sender, settings, _ = env
    t = now_hour()
    meteo.values = {t - i * H: 1012.0 for i in range(3, 30)}
    meteo.values[t] = 1005.0
    iid = str(uuid.uuid4())
    # Quiet all day except 23:59, in UTC; one minute past any hour is inside.
    register(http, iid, settings={"quiet_hours": {"enabled": True, "start": "00:00", "end": "23:59"}})
    now = t + 60
    asyncio.run(poller.evaluate_all(store, sender, settings, now=now))
    assert sender.messages == []
    alerts = http.get(f"/v1/installs/{iid}/alerts", headers=auth()).json()["alerts"]
    assert [a["status"] for a in alerts] == ["quiet_hours"]


def test_outage_pauses_alerts_and_says_so(env):
    http, store, meteo, sender, settings, client = env
    meteo.fail = True
    iid = str(uuid.uuid4())
    register(http, iid)
    pressure = http.get(f"/v1/installs/{iid}/pressure", headers=auth()).json()
    assert pressure["status"] == "unavailable"
    assert pressure["alerts_paused"] is True
    assert pressure["message"] == "Forecast unavailable, alerts paused"
    assert asyncio.run(poller.evaluate_all(store, sender, settings)) == 0


def test_unregistered_token_is_cleared(env):
    http, store, meteo, sender, settings, _ = env
    sender.status = "unregistered"
    t = now_hour()
    meteo.values = {t - i * H: 1012.0 for i in range(3, 30)}
    meteo.values[t] = 1005.0
    iid = str(uuid.uuid4())
    register(http, iid)
    asyncio.run(poller.evaluate_all(store, sender, settings))
    assert store.get_install(iid).apns_token is None


def test_moving_location_resets_state_and_garbage_collects_cell(env):
    http, store, meteo, *_ = env
    iid = str(uuid.uuid4())
    register(http, iid)
    register(http, iid, location={"latitude": 51.05, "longitude": -114.07, "name": "Calgary"})
    cells = [r["id"] for r in store.db.query("SELECT id FROM cells")]
    assert cells == [snap(51.05, -114.07, 0.1)[0]]
    assert store.get_install(iid).last_evaluated_ts is None


def test_delete_install_removes_everything(env):
    http, store, *_ = env
    iid = str(uuid.uuid4())
    register(http, iid)
    assert http.delete(f"/v1/installs/{iid}", headers=auth()).status_code == 204
    assert store.get_install(iid) is None
    assert store.db.query("SELECT * FROM cells") == []


def test_validation_rejects_bad_settings(env):
    http, *_ = env
    iid = str(uuid.uuid4())
    bad = register(http, iid, settings={"alerts": {"fall": {"short": {"hpa": 0, "hours": 3}}}})
    assert bad.status_code == 422
    assert register(http, iid, timezone="Mars/Olympus").status_code == 422


def test_apns_sender_builds_signed_request(tmp_path: Path):
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    key_path = tmp_path / "AuthKey.p8"
    key_path.write_bytes(pem)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("dead"):
            return httpx.Response(410, json={"reason": "Unregistered"})
        return httpx.Response(200)

    settings = Settings(apns_team_id="TEAM123456", apns_key_id="KEY1234567", apns_private_key_path=str(key_path))
    sender = APNsSender(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    status = asyncio.run(sender.send(PushMessage("abcd", "sandbox", "Title", "Body")))
    assert status == "sent"
    req = seen[0]
    assert str(req.url) == "https://api.sandbox.push.apple.com/3/device/abcd"
    assert req.headers["apns-topic"] == settings.apns_topic
    assert req.headers["apns-push-type"] == "alert"
    token = req.headers["authorization"].split()[1]
    claims = jwt.decode(token, key.public_key(), algorithms=["ES256"])
    assert claims["iss"] == "TEAM123456"
    assert jwt.get_unverified_header(token)["kid"] == "KEY1234567"
    body = json.loads(req.content)
    assert body["aps"]["alert"] == {"title": "Title", "body": "Body"}
    assert body["deep_link"] == "pressurealert://pressure"

    assert asyncio.run(sender.send(PushMessage("dead", "production", "T", "B"))) == "unregistered"
    assert str(seen[1].url).startswith("https://api.push.apple.com/")


def test_apns_not_configured_is_reported():
    sender = APNsSender(Settings())
    assert asyncio.run(sender.send(PushMessage("abcd", "sandbox", "T", "B"))) == "not_configured"
