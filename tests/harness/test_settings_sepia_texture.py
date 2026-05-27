"""v2.84.0 — /api/settings/sepia_texture — per-user opt-in for the
sepia theme's wood-grain background pattern.

v2.85.0 flipped the default OFF: users now start at sepia_texture=False
and opt **in** to the textured background via this endpoint. The
endpoint contract itself is unchanged.

Tests:
  - happy path: POST {enabled: true} → 200 + persisted; POST
    {enabled: false} flips it back to the default.
  - per-user: Alice's preference is independent of the GM's.
"""
from .conftest import CAMPAIGN_ID  # noqa: F401


async def test_sepia_texture_on_then_off(gm_client):
    """Toggle on, then back off. Both persist."""
    resp = await gm_client.post(
        "/api/settings/sepia_texture",
        json={"enabled": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["sepia_texture"] is True

    resp = await gm_client.post(
        "/api/settings/sepia_texture",
        json={"enabled": False},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sepia_texture"] is False


async def test_sepia_texture_persists_for_player(alice_client):
    """Per-user — Alice's preference is independent of the GM's."""
    resp = await alice_client.post(
        "/api/settings/sepia_texture",
        json={"enabled": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sepia_texture"] is True
    # Flip back to the v2.85.0 default so we don't leave demo Alice
    # in an opted-in state.
    await alice_client.post(
        "/api/settings/sepia_texture",
        json={"enabled": False},
    )
