"""In-process job queue for correction runs.

Deliberately simple: a bounded thread pool, jobs held in memory, files on local
disk. That is enough for one machine and keeps the service dependency-free. A
deployment serving many people at once wants the same interfaces backed by a
real queue and object storage -- ``JobStore`` is the seam to replace.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..config import CorrectionSettings
from ..pipeline import correct_video

log = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    filename: str
    settings: CorrectionSettings
    directory: Path
    source: Path
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    stage: str = "queued"
    result: Path | None = None
    report: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status.value,
            "progress": round(self.progress, 4),
            "stage": self.stage,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "report": self.report,
            "settings": self.settings.to_dict(),
        }


class JobStore:
    """Owns job records, their files, and the worker pool."""

    def __init__(self, workspace: Path, workers: int = 1, retain: int = 50):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.retain = retain
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        # Correction is CPU-bound, so extra workers mostly trade latency for
        # throughput. One keeps a single job as fast as possible.
        self._pool = ThreadPoolExecutor(max_workers=max(workers, 1),
                                        thread_name_prefix="gazefix")

    def submit(self, filename: str, data_path: Path, settings: CorrectionSettings) -> Job:
        """Register an already-staged upload and queue it for correction."""
        job_id = uuid.uuid4().hex
        directory = self.workspace / job_id
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / f"source{Path(filename).suffix or '.mp4'}"
        shutil.move(str(data_path), source)

        job = Job(id=job_id, filename=filename, settings=settings,
                  directory=directory, source=source)
        with self._lock:
            self._jobs[job_id] = job
        self._pool.submit(self._run, job)
        self._evict()
        return job

    def _run(self, job: Job) -> None:
        job.status = JobStatus.RUNNING
        job.stage = "starting"

        def on_progress(fraction: float, stage: str) -> None:
            job.progress = fraction
            job.stage = stage

        try:
            report = correct_video(job.source, job.directory / "corrected.mp4",
                                   job.settings, on_progress)
            job.result = Path(report.output_path)
            job.report = report.as_dict()
            job.status = JobStatus.DONE
            job.stage = "done"
            job.progress = 1.0
        except Exception as exc:  # noqa: BLE001 - surfaced to the client verbatim
            log.exception("job %s failed", job.id)
            job.status = JobStatus.FAILED
            job.stage = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = time.time()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job is None:
            return False
        shutil.rmtree(job.directory, ignore_errors=True)
        return True

    def _evict(self) -> None:
        """Drop the oldest finished jobs once the store grows past ``retain``."""
        with self._lock:
            finished = [j for j in self._jobs.values()
                        if j.status in (JobStatus.DONE, JobStatus.FAILED)]
            excess = len(self._jobs) - self.retain
            stale = sorted(finished, key=lambda j: j.created_at)[:max(excess, 0)]
            for job in stale:
                self._jobs.pop(job.id, None)
        for job in stale:
            shutil.rmtree(job.directory, ignore_errors=True)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
