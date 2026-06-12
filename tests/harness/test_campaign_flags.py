"""Harness coverage for the TEST_MODE-only campaign-flags endpoint
(``POST /api/test/campaign/{campaign_id}/flags``).

The endpoint flips campaign-level booleans (today just
``auto_apply_damage``) without driving the full multipart GM settings
form, so a test can enable a server-side damage-apply path and restore
it in a ``finally``. It only exists when the app boots with
``TEST_MODE`` set — which the harness stack does — so it's reachable
here but 404s on a production deployment.

Contract:
  - A ``None`` field leaves the flag untouched and the response echoes
    the current value (so a caller can read the original before flipping).
  - Setting ``auto_apply_damage`` mutates it and the response confirms.
  - An unknown campaign id → 404.
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID


async def test_flags_read_then_toggle_then_restore(gm_client):
    """A no-field POST reads the current value; setting then restoring
    round-trips the flag and the response echoes each state."""
    # Read current (no mutation).
    read = await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags", json={},
    )
    assert read.status_code == 200, read.text
    original = bool(read.json()["auto_apply_damage"])

    try:
        on = await gm_client.post(
            f"/api/test/campaign/{CAMPAIGN_ID}/flags",
            json={"auto_apply_damage": True},
        )
        assert on.status_code == 200, on.text
        assert on.json()["auto_apply_damage"] is True

        off = await gm_client.post(
            f"/api/test/campaign/{CAMPAIGN_ID}/flags",
            json={"auto_apply_damage": False},
        )
        assert off.status_code == 200, off.text
        assert off.json()["auto_apply_damage"] is False
    finally:
        await gm_client.post(
            f"/api/test/campaign/{CAMPAIGN_ID}/flags",
            json={"auto_apply_damage": original},
        )


async def test_flags_unknown_campaign_404(gm_client):
    """An unknown campaign id returns 404."""
    resp = await gm_client.post(
        "/api/test/campaign/999999/flags",
        json={"auto_apply_damage": True},
    )
    assert resp.status_code == 404, resp.text
