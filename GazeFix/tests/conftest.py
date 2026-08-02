"""Shared fixtures.

Tests that need the real detector are marked ``model`` and skip themselves when
the landmarker model has not been downloaded, so a checkout with no network
still runs the whole pure-logic suite.
"""

from __future__ import annotations

import numpy as np
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "model: needs the face landmarker model")


@pytest.fixture(scope="session")
def model_available() -> bool:
    from gazefix.landmarks import model_cache_dir, MODEL_FILENAME

    return (model_cache_dir() / MODEL_FILENAME).exists()


@pytest.fixture
def needs_model(model_available):
    if not model_available:
        pytest.skip("face landmarker model is not cached; run tools/fetch_model.py")


@pytest.fixture
def synthetic_clip(tmp_path):
    """A short clip of a drifting synthetic face-like pattern.

    Not a real face -- the detector finds nothing in it -- which is exactly what
    makes it useful: it exercises decode, encode and the no-face path without
    needing a person.
    """
    import cv2

    path = tmp_path / "clip.mp4"
    writer = None
    for fourcc, suffix in (("vp09", ".webm"), ("mp4v", ".mp4")):
        candidate = path.with_suffix(suffix)
        writer = cv2.VideoWriter(candidate, cv2.VideoWriter_fourcc(*fourcc), 24, (160, 120))
        if writer.isOpened():
            path = candidate
            break
        writer.release()
        writer = None
    if writer is None:
        pytest.skip("no video encoder available in this OpenCV build")

    rng = np.random.default_rng(0)
    for i in range(24):
        frame = rng.integers(0, 60, (120, 160, 3), dtype=np.uint8)
        cv2.circle(frame, (60 + i, 50), 12, (200, 200, 200), -1)
        cv2.circle(frame, (100 + i, 50), 12, (200, 200, 200), -1)
        writer.write(frame)
    writer.release()
    return path
