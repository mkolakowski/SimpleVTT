"""v2.599.10 — the campaign WebSocket rejects a user disabled mid-session.

Security-review defense-in-depth: `campaign_ws` now checks `user.is_disabled`
on connect, matching the HTTP path (`auth.get_current_user`). Without it, an
account disabled while it held a live session could keep an open socket
observing broadcasts until it disconnected.

This is a real end-to-end test: log in as a demo player (session valid), prove
the WS connects, then flip `is_disabled` in the DB *without touching the
session* and prove a fresh connect with the same session is refused — exactly
the mid-session-disable scenario. The DB toggle goes through
`docker compose exec db psql` (same precedent as `test_api_not_found_audit`),
and is always reverted in a `finally`. Skips when the stack / docker isn't
reachable or the demo user isn't present.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import httpx
import pytest

from .conftest import CAMPAIGN_ID
from .helpers import login_client, open_ws

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALICE = "demo-alice@example.com"
_PASSWORD = "demopass"
_PG_USER = "simplevtt"
_PG_DB = "simplevtt"


def _app_up() -> bool:
    try:
        return httpx.get("http://localhost:8013/healthz", timeout=3.0).status_code == 200
    except httpx.HTTPError:
        return False


def _psql(sql: str) -> str | None:
    """Run a one-off SQL statement in the db container; return stdout (str)
    or None if docker/compose/db isn't available."""
    try:
        r = subprocess.run(
            ["docker", "compose", "exec", "-T", "db",
             "psql", "-U", _PG_USER, "-d", _PG_DB, "-tA", "-c", sql],
            cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


_SKIP = pytest.mark.skipif(not _app_up(), reason="app not reachable on :8013")


@_SKIP
async def test_disabled_user_ws_rejected_mid_session():
    # Require the DB toggle path + the demo user.
    uid = _psql(f"SELECT id FROM users WHERE email='{_ALICE}'")
    if uid is None:
        pytest.skip("db not reachable via docker compose exec")
    if not uid:
        pytest.skip("demo-alice not present (non-demo stack)")

    client = await login_client(_ALICE, _PASSWORD)
    try:
        # Enabled: the WS connects (drain one message, then close).
        ws = await open_ws(client, CAMPAIGN_ID)
        await ws.recv()
        await ws.close()

        # Disable the account WITHOUT touching the (still-valid) session.
        assert _psql(f"UPDATE users SET is_disabled=true WHERE email='{_ALICE}'") is not None

        # Same session, fresh connect → handshake refused (server closes
        # before accept → the client raises during connect/first recv).
        with pytest.raises(Exception):
            ws2 = await open_ws(client, CAMPAIGN_ID)
            await ws2.recv()
            await ws2.close()
    finally:
        _psql(f"UPDATE users SET is_disabled=false WHERE email='{_ALICE}'")
        await client.aclose()
