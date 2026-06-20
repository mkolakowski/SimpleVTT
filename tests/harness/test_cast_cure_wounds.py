"""Cure Wounds — L1 evocation, Bard/Cleric/Druid/Paladin/Ranger.
Phase 2 #20 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.463.0 — RAW PHB p.230: "A creature you touch regains a
number of hit points equal to 1d8 + your spellcasting ability
modifier." 1 action, V/S, Touch, Instantaneous.

**Third mechanical non-buff cast in the Phase 2 arc** — third
bucket exemplar. Writes HP via the canonical ``_apply_hp_change``
helper so a heal at 0 HP automatically flips death-save status
back to alive (RAW revival).

Tests:
  - Heal at partial HP: response.delta > 0 and ≤ 8 + spell_mod;
    /sheet-json reads back the new HP.
  - Heal at full HP: response.delta == 0 (already capped at max).
  - Heal at 0 HP revives: status flips from dying → alive,
    response.revived == True.
  - Missing target_character_id → 400.
  - Krieger (Barbarian) caster → 409 cannot_cast.
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _get_hp(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    sheet = (r.json() or {}).get("sheet") or {}
    return dict(sheet.get("hp") or {})


async def _get_death_saves(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    sheet = (r.json() or {}).get("sheet") or {}
    return dict(sheet.get("death_saves") or {})


async def _set_hp(gm_client, char_id, hp_current):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": hp_current}},
    )
    assert r.status_code == 200, r.text


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def test_cast_cw_partial_hp_heals(gm_client, roster):
    """Drop Krieger to 5 HP, then have Tavik cast Cure Wounds.
    Response carries delta > 0, and /sheet-json shows new HP."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Krieger Stonefist"]
    try:
        # Damage Krieger down to a low HP so a heal has room.
        await _set_hp(gm_client, target["id"], 5)
        await asyncio.sleep(0.1)

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_cure_wounds",
            json={
                "character_id": cleric["id"],
                "target_character_id": target["id"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["feature"] == "cure-wounds"
        # 1d8 (1-8) + WIS mod (Tavik has WIS 16 → +3): heal_rolled in [4, 11].
        assert 1 <= body["heal_dice_total"] <= 8
        assert body["spellcasting_mod"] == 3
        # Delta is the actual HP gain (capped at max - hp_before).
        # Krieger had 5/45 → room for up to (45-5) = 40 HP. The
        # rolled heal fits, so delta == heal_dice_total + spell_mod.
        expected_delta = body["heal_dice_total"] + body["spellcasting_mod"]
        assert body["heal_rolled"] == expected_delta

        hp_after = await _get_hp(gm_client, target["id"])
        assert int(hp_after.get("current") or 0) == 5 + expected_delta
    finally:
        await _long_rest(gm_client, target["id"])


async def test_cast_cw_at_full_hp_zero_delta(gm_client, roster):
    """Cast on a target at full HP — delta == 0 (already capped)."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Krieger Stonefist"]
    try:
        await _long_rest(gm_client, target["id"])
        hp_before = await _get_hp(gm_client, target["id"])
        assert int(hp_before.get("current") or 0) == int(hp_before.get("max") or 0)

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_cure_wounds",
            json={
                "character_id": cleric["id"],
                "target_character_id": target["id"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["heal_rolled"] == 0
        assert body["hp_before"] == body["hp_after"]
    finally:
        await _long_rest(gm_client, target["id"])


async def test_cast_cw_at_zero_hp_revives(gm_client, roster):
    """Drop Caelan to 0 HP (auto-flips death_saves.status to
    dying), then heal — response.revived == True and the sheet
    reads back status='alive'.

    Caelan (Human Paladin) is the target rather than Krieger
    (Half-Orc Barbarian) because Krieger's Relentless Endurance
    racial auto-bumps him back to 1 HP on the damage event,
    blocking the dying status the test wants to observe.
    """
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Sir Caelan Lightbringer"]
    try:
        # Patch HP to 0 with damage reason so the death-save state
        # machine fires and flips status to "dying".
        r = await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{target['id']}/sheet-fields",
            json={
                "hp": {"current": 0},
                "hp_change_reason": "damage",
                "damage_amount": 100,
            },
        )
        assert r.status_code == 200, r.text
        await asyncio.sleep(0.1)
        ds = await _get_death_saves(gm_client, target["id"])
        assert ds.get("status") == "dying"

        # Now Cure Wounds: heal at 0 should revive.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_cure_wounds",
            json={
                "character_id": cleric["id"],
                "target_character_id": target["id"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["heal_rolled"] > 0
        assert body["revived"] is True

        ds_after = await _get_death_saves(gm_client, target["id"])
        assert ds_after.get("status") == "alive"
    finally:
        await _long_rest(gm_client, target["id"])


async def test_cast_cw_missing_target_returns_400(gm_client, roster):
    """Omit target_character_id → 400."""
    cleric = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_cure_wounds",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 400, r.text


async def test_cast_cw_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    target = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_cure_wounds",
        json={
            "character_id": krieger["id"],
            "target_character_id": target["id"],
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "cure wounds" in body["expected"].lower()
