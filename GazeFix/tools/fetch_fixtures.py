#!/usr/bin/env python3
"""Fetch what the model-backed tests need: the landmarker and a real face.

Both come from Google's public MediaPipe buckets. Neither is committed: the
model is 3.6 MB of weights and the portrait is somebody's photograph, so this
repo points at them instead of vendoring them.

    python tools/fetch_fixtures.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gazefix.landmarks import ensure_model  # noqa: E402

PORTRAIT_URL = "https://storage.googleapis.com/mediapipe-assets/portrait.jpg"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def main() -> int:
    model = ensure_model()
    print(f"landmarker model: {model} ({model.stat().st_size / 1e6:.1f} MB)")

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    portrait = FIXTURE_DIR / "portrait.jpg"
    if portrait.exists():
        print(f"portrait already present: {portrait}")
        return 0
    try:
        with urllib.request.urlopen(PORTRAIT_URL, timeout=60) as response:  # noqa: S310
            portrait.write_bytes(response.read())
    except OSError as exc:
        print(f"could not fetch the portrait: {exc}", file=sys.stderr)
        return 1
    print(f"portrait: {portrait} ({portrait.stat().st_size / 1e3:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
