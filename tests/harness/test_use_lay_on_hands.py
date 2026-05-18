"""/api/campaign/{cid}/use_lay_on_hands — Paladin Lay on Hands tests.

Phase 1.5 scope: error paths only. No Paladin in the demo party, so
happy-path coverage waits for either a demo Paladin (filed follow-up
to v2.10.0) or fixture characters in a sidecar test campaign (Phase 2
of the test harness plan).

Tests:
  - 400 missing fields
  - 400 amount <= 0
  - 400 self-target with character_id == target_character_id (NOT
    enforced — that's Bardic Inspiration's rule; LoH self-heals are
    legal)
  - 404 "No Lay on Hands resource on this sheet" when called against
    a non-paladin PC (Pip)
  - 404 unknown target_character_id
"""
from .conftest import CAMPAIGN_ID


async def test_loh_missing_fields(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_lay_on_hands",
        json={},
    )
    assert resp.status_code == 400


async def test_loh_zero_amount(gm_client, roster):
    """amount <= 0 returns 400."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_lay_on_hands",
        json={
            "character_id": pip["id"],
            "target_character_id": pip["id"],
            "amount": 0,
            "override": True,
        },
    )
    assert resp.status_code == 400


async def test_loh_no_paladin_resource(gm_client, roster):
    """Pip is a Rogue — no lay-on-hands resource. Endpoint returns
    404 'No Lay on Hands resource on this sheet'."""
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_lay_on_hands",
        json={
            "character_id": pip["id"],
            "target_character_id": tavik["id"],
            "amount": 5,
            "override": True,
        },
    )
    assert resp.status_code == 404
    assert "Lay on Hands" in resp.json().get("detail", "")


async def test_loh_unknown_target(gm_client, roster):
    """Target character_id that doesn't exist returns 404."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_lay_on_hands",
        json={
            "character_id": pip["id"],
            "target_character_id": 99999,
            "amount": 5,
            "override": True,
        },
    )
    assert resp.status_code == 404
