"""Mass Healing Word — L3 evocation, Bard/Cleric.
Phase 2 #24 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.467.0 — RAW PHB p.258: "As you call out words of restoration,
up to six creatures of your choice that you can see within range
regain hit points equal to 1d4 + your spellcasting ability
modifier." 1 bonus action, V, 60 ft, Instantaneous.

**First multi-target heal on the cast-and-broadcast arc.** Same
mechanical-mutation engine path as Cure Wounds (v2.463.0) and
Healing Word (v2.464.0) but wrapped in a per-target loop. The
dice are rolled once and applied to each target.

Tests:
  - Heal 3 wounded targets: per-target deltas in results;
    /sheet-json confirms each new HP.
  - Empty target list → 400.
  - 7 targets → 400 too_many_targets (RAW cap is 6).
  - Druid (Mira) → 409 cannot_cast (narrower than Healing Word's
    Bard/Cleric/Druid).
  - Unknown target_character_id → 404 target_not_found, and the
    sheet round-trip shows NO partial heals occurred (atomic).
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


async def test_cast_mhw_heals_three_targets(gm_client, roster):
    """Drop Krieger, Caelan, and Pip to low HP; Tavik casts Mass
    Healing Word on all three; each gains the same per-cast heal
    amount (capped at hp_max)."""
    cleric = roster["Brother Tavik Stonebrow"]
    t1 = roster["Krieger Stonefist"]
    t2 = roster["Sir Caelan Lightbringer"]
    t3 = roster["Pip Quickfingers"]
    try:
        for t in (t1, t2, t3):
            await _set_hp(gm_client, t["id"], 5)
        await asyncio.sleep(0.1)

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_mass_healing_word",
            json={
                "character_id": cleric["id"],
                "target_character_ids": [t1["id"], t2["id"], t3["id"]],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["feature"] == "mass-healing-word"
        assert 1 <= body["heal_dice_total"] <= 4
        assert body["spellcasting_mod"] == 3
        # heal_rolled = dice + mod, applied once to each target.
        expected_heal = body["heal_dice_total"] + body["spellcasting_mod"]
        assert body["heal_rolled"] == expected_heal

        results = body["results"]
        assert len(results) == 3
        ids_in_results = {r["target_character_id"] for r in results}
        assert ids_in_results == {t1["id"], t2["id"], t3["id"]}
        for res in results:
            # Each target was at 5 HP with plenty of room, so the
            # delta equals the rolled heal exactly.
            assert res["delta"] == expected_heal

        # Sheet round-trip: each target's HP rose by the per-cast amount.
        for t in (t1, t2, t3):
            hp_after = await _get_hp(gm_client, t["id"])
            assert int(hp_after.get("current") or 0) == 5 + expected_heal
    finally:
        for t in (t1, t2, t3):
            await _long_rest(gm_client, t["id"])


async def test_cast_mhw_empty_targets_returns_400(gm_client, roster):
    """target_character_ids=[] → 400."""
    cleric = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mass_healing_word",
        json={
            "character_id": cleric["id"],
            "target_character_ids": [],
        },
    )
    assert r.status_code == 400, r.text


async def test_cast_mhw_too_many_targets_returns_400(gm_client, roster):
    """target_character_ids with 7 entries → 400 too_many_targets."""
    cleric = roster["Brother Tavik Stonebrow"]
    # Pick any 7 ids — the over-cap check fires before any lookup.
    fake_ids = [roster[name]["id"] for name in (
        "Krieger Stonefist", "Sir Caelan Lightbringer",
        "Pip Quickfingers", "Lyra Sunstrider", "Mira Greenleaf",
        "Garrik Ironside", "Thalindra Moonwhisper",
    )]
    assert len(fake_ids) == 7
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mass_healing_word",
        json={
            "character_id": cleric["id"],
            "target_character_ids": fake_ids,
        },
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"] == "too_many_targets"
    assert body["limit"] == 6
    assert body["received"] == 7


async def test_cast_mhw_druid_rejected(gm_client, roster):
    """Mira (Druid) → 409. Mass Healing Word is Bard/Cleric only
    per RAW — narrower than Healing Word's Bard/Cleric/Druid."""
    druid = roster["Mira Greenleaf"]
    target = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mass_healing_word",
        json={
            "character_id": druid["id"],
            "target_character_ids": [target["id"]],
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "mass healing word" in body["expected"].lower()


async def test_cast_mhw_unknown_target_is_atomic(gm_client, roster):
    """An unknown target_character_id → 404 target_not_found, AND
    no partial heals are applied to the valid targets in the list.
    Verifies the up-front resolution loop bails before mutating
    any state."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Krieger Stonefist"]
    try:
        await _set_hp(gm_client, target["id"], 5)
        await asyncio.sleep(0.1)
        hp_before = await _get_hp(gm_client, target["id"])

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_mass_healing_word",
            json={
                "character_id": cleric["id"],
                "target_character_ids": [target["id"], 999_999],
            },
        )
        assert r.status_code == 404, r.text
        body = r.json()
        assert body["error"] == "target_not_found"
        assert body["target_character_id"] == 999_999

        # Atomic guarantee: Krieger's HP unchanged.
        hp_after = await _get_hp(gm_client, target["id"])
        assert int(hp_after.get("current") or 0) == int(hp_before.get("current") or 0)
    finally:
        await _long_rest(gm_client, target["id"])
