"""HTTP service: upload a clip, watch it process, compare and download."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from ..config import CorrectionSettings
from ..landmarks import FaceTracker, ensure_model
from ..pipeline import correct_image, split_comparison
from ..video import ffmpeg_path, probe
from .jobs import JobStore

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
#: Refuse uploads larger than this. Correction is slow enough that a very long
#: clip is better handled as a batch job than over a browser upload.
MAX_UPLOAD_BYTES = int(os.environ.get("GAZEFIX_MAX_UPLOAD_MB", "512")) * 1024 * 1024
ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}

VIDEO_MEDIA_TYPES = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
    ".webm": "video/webm", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
}


def _workspace() -> Path:
    configured = os.environ.get("GAZEFIX_WORKSPACE")
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "gazefix-jobs"


def create_app(workspace: Path | None = None, workers: int = 1) -> FastAPI:
    app = FastAPI(title="GazeFix", version="0.1.0",
                  description="Gaze correction for talking-head video")
    store = JobStore(workspace or _workspace(), workers=workers)
    app.state.store = store

    # One landmarker kept warm for previews. Loading the model takes about a
    # second, which is most of the latency of a preview request.
    preview_lock = threading.Lock()
    preview_tracker: list[FaceTracker] = []

    def get_preview_tracker() -> FaceTracker:
        if not preview_tracker:
            preview_tracker.append(FaceTracker(max_faces=4, video=False))
        return preview_tracker[0]

    @app.on_event("shutdown")
    def _shutdown() -> None:
        store.shutdown()
        for tracker in preview_tracker:
            tracker.close()

    def _job_or_404(job_id: str):
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="no such job")
        return job

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "ffmpeg": bool(ffmpeg_path()),
            "model_cached": ensure_model().exists(),
            "notes": [] if ffmpeg_path() else [
                "ffmpeg was not found: output will be VP9/WebM without audio, "
                "and encoding will be slower."
            ],
        }

    @app.get("/api/defaults")
    def defaults() -> dict:
        """The default settings, so the UI does not hard-code its own copy."""
        return CorrectionSettings().to_dict()

    @app.post("/api/jobs", status_code=201)
    async def create_job(
        file: UploadFile = File(...),
        settings: str = Form("{}"),
    ) -> JSONResponse:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=415,
                detail=f"unsupported file type '{suffix or file.filename}'; "
                       f"expected one of {sorted(ALLOWED_SUFFIXES)}",
            )
        try:
            parsed = CorrectionSettings.from_dict(json.loads(settings or "{}"))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"bad settings: {exc}") from exc

        staged = Path(tempfile.mkstemp(suffix=suffix)[1])
        written = 0
        try:
            with staged.open("wb") as out:
                while chunk := await file.read(1 << 20):
                    written += len(chunk)
                    if written > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                        )
                    out.write(chunk)
            if written == 0:
                raise HTTPException(status_code=422, detail="uploaded file is empty")
            try:
                probe(staged)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=422, detail=f"could not read that video: {exc}"
                ) from exc
        except Exception:
            staged.unlink(missing_ok=True)
            raise

        job = store.submit(file.filename or "clip.mp4", staged, parsed)
        return JSONResponse(job.as_dict(), status_code=201)

    @app.get("/api/jobs")
    def list_jobs() -> dict:
        return {"jobs": [job.as_dict() for job in store.list()]}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        return _job_or_404(job_id).as_dict()

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str) -> Response:
        if not store.delete(job_id):
            raise HTTPException(status_code=404, detail="no such job")
        return Response(status_code=204)

    @app.get("/api/jobs/{job_id}/source")
    def get_source(job_id: str) -> FileResponse:
        job = _job_or_404(job_id)
        return FileResponse(
            job.source,
            media_type=VIDEO_MEDIA_TYPES.get(job.source.suffix.lower(), "video/mp4"),
            filename=job.filename,
        )

    @app.get("/api/jobs/{job_id}/result")
    def get_result(job_id: str) -> FileResponse:
        job = _job_or_404(job_id)
        if job.result is None or not job.result.exists():
            raise HTTPException(status_code=409, detail=f"job is {job.status.value}")
        stem = Path(job.filename).stem
        return FileResponse(
            job.result,
            media_type=VIDEO_MEDIA_TYPES.get(job.result.suffix.lower(), "video/mp4"),
            filename=f"{stem}-gazefix{job.result.suffix}",
        )

    @app.get("/api/jobs/{job_id}/preview")
    def preview(
        job_id: str,
        t: float = Query(0.0, ge=0.0, description="timestamp in seconds"),
        mode: str = Query("split", pattern="^(before|after|split)$"),
        split: float = Query(0.5, ge=0.0, le=1.0),
    ) -> Response:
        """Correct one frame on demand, for tuning settings before committing.

        Reads from the uploaded source, so it works while the job is still
        running and reflects whatever settings the job was created with.
        """
        job = _job_or_404(job_id)
        capture = cv2.VideoCapture(str(job.source))
        if not capture.isOpened():
            raise HTTPException(status_code=422, detail="cannot read the source video")
        try:
            capture.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = capture.read()
            if not ok:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = capture.read()
        finally:
            capture.release()
        if not ok:
            raise HTTPException(status_code=422, detail="no frame at that timestamp")

        with preview_lock:
            corrected, _ = correct_image(frame, job.settings, get_preview_tracker())

        if mode == "before":
            out = frame
        elif mode == "after":
            out = corrected
        else:
            out = split_comparison(frame, corrected, split)
        ok, buffer = cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not ok:
            raise HTTPException(status_code=500, detail="could not encode the preview")
        return Response(
            content=np.asarray(buffer).tobytes(),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    uvicorn.run(
        "gazefix.server.app:app",
        host=os.environ.get("GAZEFIX_HOST", "127.0.0.1"),
        port=int(os.environ.get("GAZEFIX_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
