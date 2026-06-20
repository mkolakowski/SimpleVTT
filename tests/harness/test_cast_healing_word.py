"""Healing Word — L1 evocation, Bard/Cleric/Druid.
Phase 2 #21 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.464.0 — RAW PHB p.250: "A creature of your choice that you
can see within range regains hit points equal to 1d4 + your
spellcasting ability modifier." 1 bonus action, V, 60 ft,
Instantaneous.

Same mechanical-mutation shape as Cure Wounds (v2.463.0) but
smaller die (d4), smaller class gate (no Paladin/Ranger), and
ranged rather than touch.

Tests:
  - Heal at partial HP: response.delta in [1+mod, 4+mod];
    /sheet-json reads back the new HP.
  - Heal at full HP: delta == 0.
  - Heal at 0 HP revives: status flips dying → alive.
  - Paladin → 409 (narrower gate than Cure Wounds — asserts
    Paladin is NOT on Healing Word's RAW list).
  - Krieger (Barbarian) → 409.
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


async def test_cast_hw_partial_hp_heals(gm_client, roster):
    """Drop Krieger to 5 HP, cast Healing Word from Tavik.
    Response carries delta > 0, and /sheet-json shows new HP."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Krieger Stonefist"]
    try:
        await _set_hp(gm_client, target["id"], 5)
        await asyncio.sleep(0.1)

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_healing_word",
            json={
                "character_id": cleric["id"],
                "target_character_id": target["id"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["feature"] == "healing-word"
        # 1d4 (1-4) + WIS mod (+3): heal_rolled in [4, 7].
        assert 1 <= body["heal_dice_total"] <= 4
        assert body["spellcasting_mod"] == 3
        expected_delta = body["heal_dice_total"] + body["spellcasting_mod"]
        assert body["heal_rolled"] == expected_delta

        hp_after = await _get_hp(gm_client, target["id"])
        assert int(hp_after.get("current") or 0) == 5 + expected_delta
    finally:
        await _long_rest(gm_client, target["id"])


async def test_cast_hw_at_full_hp_zero_delta(gm_client, roster):
    """Cast on a target at full HP — delta == 0 (already capped)."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Krieger Stonefist"]
    try:
        await _long_rest(gm_client, target["id"])
        hp_before = await _get_hp(gm_client, target["id"])
        assert int(hp_before.get("current") or 0) == int(hp_before.get("max") or 0)

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_healing_word",
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


async def test_cast_hw_at_zero_hp_revives(gm_client, roster):
    """Drop Caelan to 0 HP (dying), cast Healing Word → revived.
    Uses Caelan rather than Krieger to dodge Relentless Endurance
    masking the dying state (same reason as test_cast_cw)."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Sir Caelan Lightbringer"]
    try:
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

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_healing_word",
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


async def test_cast_hw_paladin_rejected(gm_client, roster):
    """Caelan (Paladin) → 409 cannot_cast. Paladin is on the Cure
    Wounds class list but NOT on Healing Word's — asserts the
    narrower L1-evocation gate."""
    paladin = roster["Sir Caelan Lightbringer"]
    target = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_healing_word",
        json={
            "character_id": paladin["id"],
            "target_character_id": target["id"],
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "healing word" in body["expected"].lower()


async def test_cast_hw_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409."""
    krieger = roster["Krieger Stonefist"]
    target = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_healing_word",
        json={
            "character_id": krieger["id"],
            "target_character_id": target["id"],
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
