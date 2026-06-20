"""v2.477.0 — ``api.not_found`` audit event for 404 responses.

The exception handler in ``app/main.py`` emits a canonical
audit-log line for every HTTP 404, so the new ``simplevtt-scanner``
fail2ban jail can ban IPs that probe many missing paths in a
short window.

This test exercises the contract from the outside — it doesn't
verify the emission directly (that's covered by
``test_audit_log.py``), it verifies the **response codes** that
trigger the emission, and that the per-event line shape the
fail2ban filter consumes shows up in the audit log file.

The live ban test (fire 21 404s, poll fail2ban-client status)
lives in ``test_fail2ban_end_to_end.py``'s scanner-jail test and
runs only when the fail2ban profile is up.
"""
import asyncio
import subprocess

import httpx
import pytest

from .helpers import BASE_URL


async def test_unknown_path_returns_404():
    """A GET to an unknown path returns 404. The exception handler
    fires on this code path and emits ``api.not_found`` for the
    scanner jail."""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=10.0,
        follow_redirects=False,
    ) as client:
        resp = await client.get(
            "/this-path-definitely-does-not-exist-2477",
            headers={"Accept": "application/json"},
        )
    assert resp.status_code == 404


async def test_unknown_api_path_returns_404():
    """A GET to an unknown /api/* path returns 404. Same emission
    path as the bare unknown-path test."""
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=10.0,
        follow_redirects=False,
    ) as client:
        resp = await client.get(
            "/api/this-endpoint-does-not-exist-2477",
            headers={"Accept": "application/json"},
        )
    assert resp.status_code == 404


def _app_container_running() -> bool:
    """Returns True iff the app container is up — needed to read
    the audit log file via docker exec."""
    try:
        r = subprocess.run(
            ["docker", "compose", "ps", "-q", "app"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and bool(r.stdout.strip())


async def test_404_emits_canonical_audit_log_line():
    """Fire a 404 with a unique path token, then read the audit
    log inside the container and assert the canonical
    ``api.not_found ip=... path="..."`` line appears."""
    if not _app_container_running():
        pytest.skip("app container not running — can't read audit log")

    unique = "audit-marker-test-2477-abc123"
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=10.0,
        follow_redirects=False,
    ) as client:
        resp = await client.get(
            f"/{unique}",
            headers={"Accept": "application/json"},
        )
    assert resp.status_code == 404

    # The RotatingFileHandler flushes per-record by default, but
    # give it a beat to land on disk.
    await asyncio.sleep(0.5)

    # Read the last 50 lines of the audit log via docker exec
    # (the app container's path; works under non-root since
    # /var/log/simplevtt is appuser-writable after v2.474.0).
    r = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "app",
            "tail", "-n", "100", "/var/log/simplevtt/audit.log",
        ],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0, f"tail failed: {r.stderr}"
    log = r.stdout
    # The canonical line must contain the event tag + the unique
    # path. Anchors against a regression where the path is
    # dropped or the event tag is renamed.
    assert "api.not_found" in log, (
        f"audit log missing api.not_found event after a 404 GET; "
        f"recent lines:\n{log[-2000:]}"
    )
    assert unique in log, (
        f"audit log doesn't include the unique probe path "
        f"{unique!r}; recent lines:\n{log[-2000:]}"
    )
