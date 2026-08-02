"""Service-level tests.

The correction pipeline is stubbed out where the point is the HTTP contract
rather than the image processing, so these stay fast and do not need the model.
"""

from __future__ import annotations

import io
import json
import threading
import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from gazefix.config import CorrectionSettings  # noqa: E402
from gazefix.server.app import create_app  # noqa: E402
from gazefix.server.jobs import JobStatus, JobStore  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app = create_app(workspace=tmp_path / "jobs")
    with TestClient(app) as test_client:
        yield test_client


def upload(client, clip, settings=None, filename=None):
    files = {"file": (filename or clip.name, clip.read_bytes(), "video/mp4")}
    data = {"settings": json.dumps(settings or {})}
    return client.post("/api/jobs", files=files, data=data)


def wait_for(client, job_id, timeout=90.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


# ------------------------------------------------------------------ basics

def test_health_reports_its_dependencies(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert isinstance(body["ffmpeg"], bool)
    assert isinstance(body["notes"], list)


def test_defaults_match_the_library(client):
    assert client.get("/api/defaults").json()["strength"] == CorrectionSettings().strength


def test_the_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "GazeFix" in response.text


# ------------------------------------------------------------- validation

def test_a_non_video_extension_is_refused(client, tmp_path):
    fake = tmp_path / "notes.txt"
    fake.write_bytes(b"not a video")
    response = upload(client, fake)
    assert response.status_code == 415
    assert "unsupported" in response.json()["detail"]


def test_an_unreadable_video_is_refused(client, tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"\x00\x01\x02 not really an mp4")
    assert upload(client, broken).status_code == 422


def test_an_empty_upload_is_refused(client):
    response = client.post(
        "/api/jobs",
        files={"file": ("clip.mp4", io.BytesIO(b""), "video/mp4")},
        data={"settings": "{}"},
    )
    assert response.status_code == 422


def test_bad_settings_are_refused(client, synthetic_clip):
    response = upload(client, synthetic_clip, {"strength": 4.0})
    assert response.status_code == 422
    assert "bad settings" in response.json()["detail"]


def test_malformed_settings_json_is_refused(client, synthetic_clip):
    files = {"file": (synthetic_clip.name, synthetic_clip.read_bytes(), "video/mp4")}
    response = client.post("/api/jobs", files=files, data={"settings": "{not json"})
    assert response.status_code == 422


# ---------------------------------------------------------------- job flow

def test_unknown_jobs_are_not_found(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.delete("/api/jobs/nope").status_code == 404
    assert client.get("/api/jobs/nope/result").status_code == 404


def test_a_clip_runs_through_and_can_be_downloaded(client, synthetic_clip):
    created = upload(client, synthetic_clip)
    assert created.status_code == 201
    job_id = created.json()["id"]
    assert created.json()["status"] in ("queued", "running")

    finished = wait_for(client, job_id)
    assert finished["status"] == "done", finished.get("error")
    assert finished["progress"] == 1.0

    report = finished["report"]
    assert report["source"]["width"] == 160
    assert report["stats"]["frames"] > 0
    # There is no real face in the fixture, so the run should say so plainly.
    assert report["stats"]["frames_with_face"] == 0
    assert any("no face" in w.lower() for w in report["warnings"])

    result = client.get(f"/api/jobs/{job_id}/result")
    assert result.status_code == 200
    assert len(result.content) > 0
    assert "attachment" in result.headers["content-disposition"]
    assert "gazefix" in result.headers["content-disposition"]


def test_the_original_stays_available(client, synthetic_clip):
    job_id = upload(client, synthetic_clip).json()["id"]
    response = client.get(f"/api/jobs/{job_id}/source")
    assert response.status_code == 200
    assert response.content == synthetic_clip.read_bytes()


def test_settings_are_carried_through_to_the_report(client, synthetic_clip):
    created = upload(client, synthetic_clip, {"strength": 0.4, "lens_position": [0.5, 0.1]})
    report = wait_for(client, created.json()["id"])["report"]
    assert report["settings"]["strength"] == 0.4
    assert report["settings"]["lens_position"] == [0.5, 0.1]


def test_results_are_unavailable_until_the_job_finishes(client, synthetic_clip, monkeypatch):
    """Asking early is a conflict, not a 404."""
    release = threading.Event()

    def block_until_released(*args, **kwargs):
        release.wait(30)
        raise RuntimeError("released")

    monkeypatch.setattr("gazefix.server.jobs.correct_video", block_until_released)

    job_id = upload(client, synthetic_clip).json()["id"]
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            if client.get(f"/api/jobs/{job_id}").json()["status"] == "running":
                break
            time.sleep(0.05)
        response = client.get(f"/api/jobs/{job_id}/result")
        assert response.status_code == 409
        assert "running" in response.json()["detail"]
    finally:
        release.set()


def test_listing_and_deleting(client, synthetic_clip):
    job_id = upload(client, synthetic_clip).json()["id"]
    wait_for(client, job_id)

    listed = client.get("/api/jobs").json()["jobs"]
    assert any(job["id"] == job_id for job in listed)

    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_preview_returns_a_jpeg(client, synthetic_clip):
    job_id = upload(client, synthetic_clip).json()["id"]
    response = client.get(f"/api/jobs/{job_id}/preview", params={"t": 0.1, "mode": "split"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content[:2] == b"\xff\xd8"  # JPEG start of image


def test_preview_rejects_an_unknown_mode(client, synthetic_clip):
    job_id = upload(client, synthetic_clip).json()["id"]
    assert client.get(f"/api/jobs/{job_id}/preview", params={"mode": "sideways"}).status_code == 422


def test_preview_past_the_end_falls_back_to_the_first_frame(client, synthetic_clip):
    job_id = upload(client, synthetic_clip).json()["id"]
    response = client.get(f"/api/jobs/{job_id}/preview", params={"t": 9999.0})
    assert response.status_code == 200


# ------------------------------------------------------------- job store

def test_a_failing_run_is_recorded_not_raised(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("encoder went home")

    monkeypatch.setattr("gazefix.server.jobs.correct_video", explode)
    store = JobStore(tmp_path / "store")
    staged = tmp_path / "staged.mp4"
    staged.write_bytes(b"pretend video")
    job = store.submit("clip.mp4", staged, CorrectionSettings())

    deadline = time.time() + 10
    while job.status not in (JobStatus.DONE, JobStatus.FAILED) and time.time() < deadline:
        time.sleep(0.05)
    assert job.status is JobStatus.FAILED
    assert "encoder went home" in job.error
    store.shutdown()


def test_the_store_evicts_old_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr("gazefix.server.jobs.correct_video", lambda *a, **k: explode_never())
    store = JobStore(tmp_path / "store", retain=2)
    for i in range(5):
        staged = tmp_path / f"staged{i}.mp4"
        staged.write_bytes(b"x")
        store.submit(f"clip{i}.mp4", staged, CorrectionSettings())
        time.sleep(0.02)
    time.sleep(0.5)
    assert len(store.list()) <= 3
    store.shutdown()


def explode_never():
    raise RuntimeError("stub")
