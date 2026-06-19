"""Spare the Dying — cantrip necromancy, Cleric.
Phase 2 #18 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.461.0 — RAW PHB p.277: "You touch a living creature that has
0 hit points. The creature becomes stable." 1 action, V/S,
Touch, Instantaneous.

**First mechanical non-buff cast in the Phase 2 arc.** Unlike
Identify (v2.459.0) and Purify Food and Drink (v2.460.0) — both
broadcast-only — Spare the Dying actually mutates engine state:
it flips the target's death_saves.status to "stable" (zeroing
successes + failures) and broadcasts the canonical
character_death_save event.

Tests:
  - Target at 0 HP: cast succeeds → response.stabilized = True,
    death_saves.status = "stable", successes + failures both 0.
  - Target above 0 HP: 409 target_not_at_zero_hp.
  - Missing target_character_id: 400.
  - Non-cleric (Wizard): 409 cannot_cast.
  - Sheet snapshot: the target's stored death_saves.status flips
    to "stable" after the cast (asserts the DB commit landed).
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _get_hp(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    sheet = (r.json() or {}).get("sheet") or {}
    return int((sheet.get("hp") or {}).get("current") or 0)


async def _get_death_saves(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    sheet = (r.json() or {}).get("sheet") or {}
    return dict(sheet.get("death_saves") or {})


async def _set_hp(gm_client, char_id, hp_current, hp_max=None):
    body = {"hp": {"current": hp_current}}
    if hp_max is not None:
        body["hp"]["max"] = hp_max
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


async def _long_rest(gm_client, char_id):
    """Restore HP + death-save state to baseline for the next test."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def test_cast_std_stabilizes_target_at_zero_hp(gm_client, roster):
    """Drop Krieger to 0 HP, then have Tavik cast Spare the Dying on
    him. Response should carry stabilized=True and death_saves
    should show status='stable' with both counters zeroed."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Krieger Stonefist"]
    try:
        await _set_hp(gm_client, target["id"], 0)
        await asyncio.sleep(0.1)  # let the sheet PATCH settle

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spare_the_dying",
            json={
                "character_id": cleric["id"],
                "target_character_id": target["id"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["feature"] == "spare-the-dying"
        assert body["stabilized"] is True
        assert body["target_character_id"] == target["id"]
        ds = body["death_saves"]
        assert ds["status"] == "stable"
        assert ds["successes"] == 0
        assert ds["failures"] == 0

        # Verify the DB commit landed: re-read the target's sheet.
        ds_after = await _get_death_saves(gm_client, target["id"])
        assert ds_after.get("status") == "stable"
    finally:
        await _long_rest(gm_client, target["id"])


async def test_cast_std_rejects_target_above_zero_hp(gm_client, roster):
    """Target above 0 HP → 409 target_not_at_zero_hp. RAW requires
    the target to be at 0 HP."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Krieger Stonefist"]
    try:
        # Long-rest puts Krieger at max HP > 0.
        await _long_rest(gm_client, target["id"])
        hp_before = await _get_hp(gm_client, target["id"])
        assert hp_before > 0

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spare_the_dying",
            json={
                "character_id": cleric["id"],
                "target_character_id": target["id"],
            },
        )
        assert r.status_code == 409, r.text
        body = r.json()
        assert body["error"] == "target_not_at_zero_hp"
        assert body["got_hp_current"] == hp_before
    finally:
        await _long_rest(gm_client, target["id"])


async def test_cast_std_missing_target_returns_400(gm_client, roster):
    """Omit target_character_id → 400."""
    cleric = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spare_the_dying",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 400, r.text


async def test_cast_std_non_cleric_rejected(gm_client, roster):
    """Wizard (non-cleric) → 409 cannot_cast. Spare the Dying is a
    Cleric cantrip per RAW (Artificer also has it but Artificer
    isn't SRD; we gate cleric-only here)."""
    wiz = roster["Thalindra Moonwhisper"]
    target = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spare_the_dying",
        json={
            "character_id": wiz["id"],
            "target_character_id": target["id"],
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "spare the dying" in body["expected"].lower()
