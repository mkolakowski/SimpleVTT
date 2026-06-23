"""Demo multi-campaign shape (v2.591.0+).

Tracks the demo-rework arc: five leveled sample campaigns (levels 3/5/9/13/18),
shared players, and a second GM (demo-gm2) who owns one campaign. This file
grows as each campaign lands (phases D3–D6); for now it locks in the expanded
user roster from phase D2. Live-only — skips when the app isn't reachable.
"""
import httpx
import pytest

from .helpers import BASE_URL, login_client

_DEMO_ACCOUNTS = [
    "demo-gm@example.com",
    "demo-alice@example.com",
    "demo-bob@example.com",
    "demo-gm2@example.com",
    "demo-carol@example.com",
    "demo-dave@example.com",
    "demo-erin@example.com",
]


def _app_up() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/healthz", timeout=3.0).status_code == 200
    except httpx.HTTPError:
        return False


_LIVE = pytest.mark.skipif(not _app_up(), reason="app not reachable on :8013")


@_LIVE
@pytest.mark.parametrize("email", _DEMO_ACCOUNTS)
async def test_demo_account_can_log_in(email):
    """Every seeded demo account (3 original + demo-gm2 + 3 new players)
    logs in with the shared demo password."""
    client = await login_client(email, "demopass")
    try:
        # The lobby renders for an authed user (200, not a bounce to /login).
        resp = await client.get("/")
        assert resp.status_code == 200, f"{email}: {resp.status_code}"
    finally:
        await client.aclose()
