"""Demo-mode reset scheduler (v2.3.0).

In-process asyncio task that runs ``app.demo_seed.reset_and_reseed`` on
a fixed interval. Kept as a small standalone module so the lifespan
handler stays readable.

Lifecycle:
- ``start_demo_scheduler(app)`` registers a background task on the
  running event loop. The task lives until the app shuts down.
- Each iteration: ``await asyncio.sleep(interval); reset_and_reseed()``.
- Errors are caught + logged so a single failure doesn't kill the
  loop (the next iteration will retry).
- The task is also stored on ``app.state.demo_scheduler_task`` so the
  shutdown hook can cancel it cleanly.

Configurable via ``DEMO_RESET_INTERVAL_MINUTES`` (clamped to [5, 1440]
by config.py).

Reset reference time: the task records the next-reset wall-clock time
on ``app.state.demo_next_reset`` so the banner countdown reads from a
single source.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from .database import SessionLocal

log = logging.getLogger(__name__)


def start_demo_scheduler(app) -> None:
    """Spawn the reset loop as a background asyncio task."""
    from .config import get_settings
    settings = get_settings()
    interval_min = max(5, min(1440, int(settings.demo_reset_interval_minutes or 60)))
    interval_s = interval_min * 60

    async def _loop():
        log.info("demo scheduler: %d-minute reset loop started", interval_min)
        while True:
            app.state.demo_next_reset = datetime.utcnow() + timedelta(seconds=interval_s)
            try:
                await asyncio.sleep(interval_s)
            except asyncio.CancelledError:
                log.info("demo scheduler: cancelled")
                return
            try:
                from .demo_seed import reset_and_reseed
                with SessionLocal() as db:
                    counts = reset_and_reseed(db)
                log.info("demo scheduler: scheduled reset complete: %s", counts)
            except Exception as e:  # noqa: BLE001 — never let the loop die
                log.exception("demo scheduler: reset failed: %s", e)

    app.state.demo_next_reset = datetime.utcnow() + timedelta(seconds=interval_s)
    task = asyncio.create_task(_loop())
    app.state.demo_scheduler_task = task


def stop_demo_scheduler(app) -> None:
    """Cancel the reset loop (called from the lifespan shutdown half)."""
    task = getattr(app.state, "demo_scheduler_task", None)
    if task is not None and not task.done():
        task.cancel()
