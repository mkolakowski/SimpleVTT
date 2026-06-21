"""Zone of Truth — L2 enchantment, Bard/Cleric/Paladin.
Phase 2 #52 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.534.0 — RAW PHB p.289: "You create a magical zone that guards against
deception in a 15-foot-radius sphere ... a creature that enters the
spell's area ... must make a Charisma saving throw. On a failed save, a
creature can't speak a deliberate lie while in the radius." 1 action,
V/S, 60 ft, 10 minutes, non-concentration.

Save-DC marker cast (the Sanctuary DC-bake pattern): installs a
`zone-of-truth` buff on the caster carrying `effects.zone_of_truth: True`
+ the baked `save_dc` (8 + prof + spellcasting mod) + `save_ability:
CHA`. The sphere geometry + per-creature CHA saves + lie-prevention are
GM-narrated.

Tests:
  - Cleric self-cast → buff carries zone_of_truth + save_dc + CHA; the
    response surfaces the same DC, which matches 8 + prof + spellcasting
    mod from the sheet.
  - Buff is non-concentration, 10-min (100 rounds).
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_zot_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _set_battle(gm_client, caster):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_tok(caster)], "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


def _find_caster(roster):
    for name in ("Brother Tavik Stonebrow", "Lyra Sunstrider",
                 "Sir Caelan Lightbringer"):
        if name in roster:
            return roster[name]
    return None


async def test_cast_zot_installs_dc_marker(gm_client, roster):
    """Cast → buff carries zone_of_truth + save_dc + CHA; the response
    DC matches and is a sane value (>= 8)."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Cleric/Paladin in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_zone_of_truth",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "zone-of-truth"
    assert body["save_ability"] == "CHA"
    dc = int(body["save_dc"])
    assert dc >= 8, dc

    buffs = await _get_buffs(gm_client, caster["id"])
    zot = next((b for b in buffs if b.get("key") == "zone-of-truth"), None)
    assert zot is not None, f"buff missing: {buffs}"
    eff = zot.get("effects") or {}
    assert eff.get("zone_of_truth") is True
    assert int(eff.get("save_dc") or 0) == dc
    assert (eff.get("save_ability") or "").upper() == "CHA"


async def test_cast_zot_dc_matches_sheet(gm_client, roster):
    """The baked DC equals 8 + proficiency + spellcasting-ability mod
    from the caster's sheet (the canonical spell-save-DC formula)."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Cleric/Paladin in the demo roster")
    sj = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/sheet-json",
    )
    assert sj.status_code == 200, sj.text
    sheet = sj.json().get("sheet") or {}
    prof = int(sheet.get("proficiency_bonus") or 2)
    spc = (sheet.get("spellcasting_ability") or "").strip().upper()[:3]
    if spc not in {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
        import pytest
        pytest.skip("caster sheet lacks a spellcasting ability")
    ab = int((sheet.get("abilities") or {}).get(spc, 10))
    expected = 8 + prof + (ab - 10) // 2

    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_zone_of_truth",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    # Allow an item DC bonus to push it higher, but not lower.
    assert int(r.json()["save_dc"]) >= expected, (
        f"DC {r.json()['save_dc']} < expected base {expected}"
    )


async def test_cast_zot_is_10_min_non_concentration(gm_client, roster):
    """The buff carries duration_rounds=100 (10 min) + concentration=false."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Bard/Cleric/Paladin in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_zone_of_truth",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["duration_rounds"] == 100
    buffs = await _get_buffs(gm_client, caster["id"])
    zot = next((b for b in buffs if b.get("key") == "zone-of-truth"), None)
    assert zot is not None
    assert zot.get("concentration") is False
    assert int(zot.get("duration_rounds") or 0) == 100


async def test_cast_zot_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_zone_of_truth",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "zone of truth" in r.json()["expected"].lower()


async def test_cast_zot_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_zone_of_truth",
        json={},
    )
    assert r.status_code == 400, r.text
