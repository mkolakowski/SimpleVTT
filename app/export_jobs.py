"""In-memory export-job registry for the async campaign/character export.

Phase 4 of the backup/export-import arc
(``docs/plans/backup-export-overhaul.md``). A campaign zip can bundle tens
of MB of media, so the export runs as a background job: the POST returns a
``job_id`` immediately, the client polls ``GET /api/export-jobs/{id}`` for
progress, then downloads the finished zip. SimpleVTT runs as a single app
container, so a process-local dict (guarded by a lock, since the build runs
in the threadpool while polls read on the event loop) suffices — the same
single-container rationale as ``app/export_limit.py``.

Jobs are swept after a TTL so a finished-but-never-downloaded archive doesn't
leak disk. FastAPI-free so the lifecycle is unit-testable host-side.
"""
from __future__ import annotations

import os
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

# Finished/errored jobs (and their staged zips) are reclaimed this long after
# completion. Overridable so a test can force prompt sweeping.
def _ttl_seconds() -> int:
    raw = os.environ.get("EXPORT_JOB_TTL_SECONDS", "1800").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1800


@dataclass
class JobState:
    job_id: str
    owner_user_id: int
    created_at: float
    status: str = "running"   # running | done | error
    progress: int = 0          # 0..100
    stage: str = "starting"
    error: Optional[str] = None
    zip_path: Optional[str] = None
    filename: Optional[str] = None

    def public(self) -> dict:
        """The poll-facing view (never leaks the on-disk staging path)."""
        d = asdict(self)
        d.pop("zip_path", None)
        d.pop("owner_user_id", None)
        d["download_url"] = (
            f"/api/export-jobs/{self.job_id}/download" if self.status == "done" else None
        )
        return d


_JOBS: dict[str, JobState] = {}
_LOCK = threading.Lock()


def new_job(owner_user_id: int, *, now: float) -> JobState:
    """Register a fresh running job and return it. ``job_id`` is a random
    hex token so it isn't guessable from the campaign id."""
    job = JobState(job_id=uuid.uuid4().hex, owner_user_id=owner_user_id, created_at=now)
    with _LOCK:
        _JOBS[job.job_id] = job
    return job


def get(job_id: str) -> Optional[JobState]:
    with _LOCK:
        return _JOBS.get(job_id)


def update(job_id: str, *, progress: Optional[int] = None, stage: Optional[str] = None) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        if progress is not None:
            job.progress = max(0, min(100, int(progress)))
        if stage is not None:
            job.stage = stage


def finish(job_id: str, *, zip_path: str, filename: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job.status = "done"
        job.progress = 100
        job.stage = "done"
        job.zip_path = zip_path
        job.filename = filename


def fail(job_id: str, *, error: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job.status = "error"
        job.error = error
        job.stage = "error"


def sweep(*, now: float) -> int:
    """Drop finished/errored jobs older than the TTL and unlink their staged
    zips. Returns the number of jobs reclaimed. Cheap to call on each poll."""
    ttl = _ttl_seconds()
    reclaimed = 0
    with _LOCK:
        for jid in list(_JOBS):
            job = _JOBS[jid]
            if job.status in ("done", "error") and (now - job.created_at) > ttl:
                if job.zip_path:
                    try:
                        Path(job.zip_path).unlink(missing_ok=True)
                    except OSError:
                        pass
                del _JOBS[jid]
                reclaimed += 1
    return reclaimed
