"""Dice-seed helper for the encounter-sim suite.

Thin wrapper over the v2.49.12 ``POST /api/test/dice/seed`` endpoint
so tests don't have to remember the URL or the JSON shape. The
endpoint only exists when ``TEST_MODE=true`` (the harness CI job
sets it; production never does).
"""
from __future__ import annotations

import os

import httpx


BASE_URL = os.getenv("HARNESS_BASE_URL", "http://localhost:8013")


def set_dice_seed(seed: int | None) -> None:
    """Re-seed the server's shared dice RNG.

    Pass an integer for reproducible rolls; ``None`` returns the RNG
    to OS entropy. Raises if the endpoint isn't reachable — the
    fixture caller is expected to run against a TEST_MODE-on stack.
    """
    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        resp = client.post("/api/test/dice/seed", json={"seed": seed})
        if resp.status_code == 404:
            raise RuntimeError(
                "POST /api/test/dice/seed returned 404 — is TEST_MODE=true "
                "in the stack's .env? The endpoint only mounts when set."
            )
        resp.raise_for_status()
