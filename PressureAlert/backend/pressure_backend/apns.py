"""Apple Push Notification service sender, token-based (.p8) auth over HTTP/2."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import httpx
import jwt

from .config import Settings

HOSTS = {
    "production": "https://api.push.apple.com",
    "sandbox": "https://api.sandbox.push.apple.com",
}

# Apple rejects provider tokens older than an hour and throttles refreshes
# more often than every 20 minutes.
TOKEN_LIFETIME = 50 * 60

SendStatus = Literal["sent", "unregistered", "failed", "not_configured"]


@dataclass(frozen=True)
class PushMessage:
    device_token: str
    environment: str
    title: str
    body: str
    deep_link: str = "pressurealert://pressure"
    thread_id: str = "pressure-alerts"


class PushSender(Protocol):
    async def send(self, message: PushMessage) -> SendStatus: ...


def payload(message: PushMessage) -> dict:
    return {
        "aps": {
            "alert": {"title": message.title, "body": message.body},
            "sound": "default",
            "thread-id": message.thread_id,
        },
        "deep_link": message.deep_link,
    }


class APNsSender:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.http = http or httpx.AsyncClient(http2=True, timeout=15)
        self._key: str | None = None
        self._token: str | None = None
        self._token_at = 0.0

    def _provider_token(self) -> str:
        now = time.time()
        if self._token and now - self._token_at < TOKEN_LIFETIME:
            return self._token
        if self._key is None:
            self._key = Path(self.settings.apns_private_key_path).read_text()
        self._token = jwt.encode(
            {"iss": self.settings.apns_team_id, "iat": int(now)},
            self._key,
            algorithm="ES256",
            headers={"kid": self.settings.apns_key_id},
        )
        self._token_at = now
        return self._token

    async def send(self, message: PushMessage) -> SendStatus:
        if not self.settings.apns_configured:
            return "not_configured"
        host = HOSTS.get(message.environment, HOSTS["production"])
        try:
            response = await self.http.post(
                f"{host}/3/device/{message.device_token}",
                json=payload(message),
                headers={
                    "authorization": f"bearer {self._provider_token()}",
                    "apns-topic": self.settings.apns_topic,
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                },
            )
        except httpx.HTTPError:
            return "failed"
        if response.status_code == 200:
            return "sent"
        reason = ""
        try:
            reason = response.json().get("reason", "")
        except ValueError:
            pass
        if response.status_code == 410 or reason in {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}:
            return "unregistered"
        return "failed"

    async def aclose(self) -> None:
        await self.http.aclose()
