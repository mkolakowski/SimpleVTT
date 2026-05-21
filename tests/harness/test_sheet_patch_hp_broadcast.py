"""PATCH /sheet-fields HP changes broadcast character_hp_update.

v2.49.42 fix. Before this fix, the PATCH path only broadcast
``character_death_save`` on status_changed crossings (entering /
leaving the dying / stable / dead states). Vanilla HP changes
within ``alive`` (e.g. 35 → 25) went silent — non-GM clients had
no signal to update their local battle state's HP.

Surfaced by the encounter-sim test_alice_observes_hp_update
(v2.49.35), which originally tried to use PATCH /sheet-fields to
damage Pip from Alice's observer test but found no broadcast
arrived. The test was rewritten to use /attack instead, but the
underlying gap remained — until now.

Tests:
  - HP drop within alive (no status change) fires character_hp_update.
  - HP set back to max (heal) fires character_hp_update with
    positive delta.
  - HP set with no change (no-op) does NOT fire the broadcast.
"""
from .conftest import CAMPAIGN_ID


async def test_hp_drop_within_alive_broadcasts(gm_client, gm_ws, roster):
    """Pip at 35/35 takes 10 damage; status stays "alive". Broadcast
    fires character_hp_update with delta=-10."""
    pip = roster["Pip Quickfingers"]
    # Long-rest to ensure starting HP is at max for the delta math.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    gm_ws.mark()

    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={
            "hp": {"current": 25},
            "hp_change_reason": "damage",
            "damage_amount": 10,
        },
    )
    assert resp.status_code == 200, resp.text

    msg = await gm_ws.wait_for("character_hp_update", timeout=3.0)
    assert msg["data"]["character_id"] == pip["id"]
    assert msg["data"]["hp"]["current"] == 25
    # Source label distinguishes /attack from sheet-patch updates.
    assert msg["data"]["source"] == "sheet_patch"
    # Delta is negative for damage.
    assert msg["data"]["delta"] < 0


async def test_hp_heal_broadcasts_positive_delta(gm_client, gm_ws, roster):
    """PATCH HP up (heal) fires character_hp_update with positive delta."""
    pip = roster["Pip Quickfingers"]
    # First damage Pip to <max so the heal back to max has a delta.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"hp": {"current": 20}},
    )
    gm_ws.mark()

    # Now heal Pip back up.
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"hp": {"current": 35}},
    )
    assert resp.status_code == 200, resp.text

    msg = await gm_ws.wait_for("character_hp_update", timeout=3.0)
    assert msg["data"]["hp"]["current"] == 35
    assert msg["data"]["delta"] > 0
    assert msg["data"]["source"] == "sheet_patch"


async def test_hp_unchanged_does_not_broadcast(gm_client, gm_ws, roster):
    """PATCH with current=current (no-op) doesn't fire character_hp_update.
    Otherwise every settings-form PATCH would spam the channel.
    """
    import asyncio
    pip = roster["Pip Quickfingers"]
    # Long-rest puts Pip at max HP. Read the actual value back rather
    # than hardcoding it (demo seed values shift over time).
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    roster_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/roster")
    pip_now = next(c for c in roster_resp.json()["characters"] if c["id"] == pip["id"])
    current = int(pip_now["hp_current"])
    gm_ws.mark()

    # PATCH HP to the value it already has — should be a no-op for
    # the broadcast.
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"hp": {"current": current}},
    )
    assert resp.status_code == 200

    # Wait a moment for any spurious broadcast to arrive.
    await asyncio.sleep(0.3)
    spurious = gm_ws.buffered("character_hp_update")
    assert not spurious, (
        f"PATCH with HP unchanged should not broadcast character_hp_update; "
        f"got {len(spurious)}: {spurious}"
    )
