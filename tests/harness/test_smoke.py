"""Smoke tests — confirm the demo stack is reachable and the roster
fixture works before anything else runs."""
import httpx
import pytest


async def test_healthz():
    """The app is up and serving /healthz."""
    async with httpx.AsyncClient(base_url="http://localhost:8013") as client:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("ok") is True
        assert "app_version" in body


async def test_version():
    """The /version endpoint returns the app + schema version."""
    async with httpx.AsyncClient(base_url="http://localhost:8013") as client:
        resp = await client.get("/version")
        assert resp.status_code == 200
        body = resp.json()
        assert "app_version" in body
        assert "schema_version" in body


async def test_roster_fixture(roster):
    """The demo roster has the three expected PCs."""
    assert "Pip Quickfingers" in roster
    assert "Thalindra Moonwhisper" in roster
    assert "Brother Tavik Stonebrow" in roster
    # Sanity-check shape per character.
    pip = roster["Pip Quickfingers"]
    assert isinstance(pip["id"], int)
    assert "hp_current" in pip
    assert "hp_max" in pip


async def test_gm_can_open_ws(gm_ws):
    """GM session can open a campaign WS and the collector
    initializes without exceptions. Buffered messages after the
    300ms drain should be empty (we cleared the cursor)."""
    assert gm_ws.buffered() == []
