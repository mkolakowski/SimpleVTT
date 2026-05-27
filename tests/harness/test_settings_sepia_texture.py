"""v2.84.0 — /api/settings/sepia_texture — per-user opt-in for the
sepia theme's wood-grain background pattern. Default ON.

Tests:
  - happy path: POST {enabled: false} → 200 + persisted; POST
    {enabled: true} flips it back.
  - per-user: Alice's preference is independent of the GM's.
"""
from .conftest import CAMPAIGN_ID  # noqa: F401


async def test_sepia_texture_off_then_on(gm_client):
    """Toggle off, then back on. Both persist."""
    resp = await gm_client.post(
        "/api/settings/sepia_texture",
        json={"enabled": False},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["sepia_texture"] is False

    resp = await gm_client.post(
        "/api/settings/sepia_texture",
        json={"enabled": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sepia_texture"] is True


async def test_sepia_texture_persists_for_player(alice_client):
    """Per-user — Alice's preference is independent of the GM's."""
    resp = await alice_client.post(
        "/api/settings/sepia_texture",
        json={"enabled": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sepia_texture"] is False
    # Flip back so we don't leave demo Alice in a non-default state.
    await alice_client.post(
        "/api/settings/sepia_texture",
        json={"enabled": True},
    )
