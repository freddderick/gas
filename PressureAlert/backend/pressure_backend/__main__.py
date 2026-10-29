"""Command line entry point.

    pressure-backend serve [--host 127.0.0.1] [--port 8000]
    pressure-backend fetch-once      # one fetch + evaluate pass, then exit
    pressure-backend evaluate-once   # evaluate against stored series only
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from .apns import APNsSender
from .config import load_settings
from .db import Database
from .openmeteo import OpenMeteoClient
from . import poller
from .store import Store


def main() -> None:
    parser = argparse.ArgumentParser(prog="pressure-backend")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("fetch-once")
    sub.add_parser("evaluate-once")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()

    if args.command == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(settings), host=args.host, port=args.port, proxy_headers=True)
        return

    async def once() -> None:
        store = Store(Database(settings.database_path))
        client, sender = OpenMeteoClient(settings), APNsSender(settings)
        try:
            if args.command == "fetch-once":
                await poller.fetch_all(store, client, settings)
            sent = await poller.evaluate_all(store, sender, settings)
            logging.info("sent %d notifications", sent)
        finally:
            await client.aclose()
            await sender.aclose()

    asyncio.run(once())


if __name__ == "__main__":
    main()
