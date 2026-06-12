"""Phase 4 — Spiritual Weapon deep-dive (the upcast-scaling contract).

Spiritual Weapon (PHB p.278) is the Cleric's bonus-action floating
attacker: "you create a floating, spectral weapon … you can make a melee
spell attack against a creature within 5 feet … On a hit, the target
takes force damage equal to 1d8 + your spellcasting ability modifier."
Upcast: "the damage increases by 1d8 for every two slot levels above the
2nd." The engine models this on the dedicated `/use_spiritual_weapon`
endpoint (tabletop_routes.py:51858): it stands up the weapon combatant,
makes a 1d20 + prof + spellcasting-mod attack vs the target's AC, and on
a hit rolls ``n``d8 + mod force where ``n = 1 + (slot_level - 2) // 2``.

The summon / concentration-lifetime / single-attack lifecycle is already
fenced by `test_use_spiritual_weapon.py` (summon-only, the
concentration-drop dismiss cascade, summon + force-damage attack). This
file owns the two parts that file doesn't:

  - the *upcast dice scaling* — at the base 2nd-level slot a hit rolls a
    single d8 (1d8 + mod, so 1+mod..8+mod); cast at a 4th-level slot a
    hit can exceed 8+mod, which is impossible for one d8 — proving the
    "+1d8 per two slot levels" tier added a second die;
  - the *house-rule concentration binding* — the catalog flags Spiritual
    Weapon ``concentration: false`` (RAW it needs no concentration), but
    this VTT binds the weapon to the caster's concentration so it lives
    only while concentration holds; the cast broadcasts a
    ``concentration_update`` for "Spiritual Weapon" and the weapon
    combatant comes back ``concentration_bound: true``.

Caster: Brother Tavik Stonebrow (demo Cleric) — knows Spiritual Weapon,
spellcasting mod read from the live sheet so the damage bands track the
seed shape. The endpoint doesn't gate on spell slots, so the 4th-level
upcast cast needs no L4 slot on the sheet.
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_CASTER = "Brother Tavik Stonebrow"
_SLUG = "spiritual-weapon"


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    return next(t for t in r.json() if "bandit" in t["name"].lower())


async def _sheet(gm_client, char_id) -> dict:
    return (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json")
    ).json().get("sheet") or {}


def _spc_mod(sheet: dict) -> int:
    spc = (sheet.get("spellcasting_ability")
           or sheet.get("class_spellcasting") or "WIS").strip().upper()[:3]
    if spc not in {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
        spc = "WIS"
    return (int((sheet.get("abilities") or {}).get(spc, 10)) - 10) // 2


def _pc_cb(c):
    return {
        "id": f"tok_sw_{c['id']}", "char_id": c["id"], "name": c["name"],
        "initiative": 12, "hp_current": 40, "hp_max": 40, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, caster, bandit_id):
    bandit = await _bandit_tmpl(gm_client)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc_cb(caster),
            {"id": bandit_id, "char_id": None,
             "token_template_id": bandit["id"], "name": "SW Target",
             "initiative": 7, "hp_current": 999, "hp_max": 999, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _cast(gm_client, caster_id, slot_level, target_id=None):
    body = {"character_id": caster_id, "x": 700.0, "y": 700.0,
            "slot_level": slot_level}
    if target_id is not None:
        body["target_combatant_id"] = target_id
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spiritual_weapon", json=body,
    )


async def _seed_dice(gm_client, seed) -> None:
    await gm_client.post("/api/test/dice/seed", json={"seed": seed})


async def _dismiss(gm_client, combatant_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
        json={"combatant_id": combatant_id},
    )


async def _clear_concentration(gm_client, char_id):
    await gm_client.delete(
        f"/api/campaign/{CAMPAIGN_ID}/concentration/{char_id}",
    )


async def _hit_damage_at(gm_client, caster, bandit_id, slot_level, max_seeds=80):
    """Loop dice seeds (fresh weapon each cast) until the weapon hits;
    return the hit response. Dismisses every weapon so the board doesn't
    accumulate."""
    for seed in range(1, max_seeds):
        await _seed_dice(gm_client, seed)
        await _seed_battle(gm_client, caster, bandit_id)
        r = await _cast(gm_client, caster["id"], slot_level, bandit_id)
        assert r.status_code == 200, r.text
        data = r.json()
        await _dismiss(gm_client, data["combatant"]["id"])
        if data.get("hit"):
            return data
    return None


async def test_spiritual_weapon_present_in_catalog():
    """Catalog anchor — Spiritual Weapon present as a 2nd-level
    bonus-action melee spell-attack cantrip-shaped action (1d8 force,
    attack_roll true), with the upcast note documenting the +1d8-per-two-
    levels scaling this gate depends on."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    assert _SLUG in by_slug, "spiritual-weapon absent from catalog"
    spell = by_slug[_SLUG]
    assert int(spell.get("level_int") or 0) == 2, spell.get("level_int")
    assert "bonus action" in (spell.get("casting_time") or "").lower(), spell
    action = next(a for a in spell["actions"] if a.get("damage"))
    assert action.get("attack_roll") is True, action
    assert (action.get("damage") or "") == "1d8", action
    assert (action.get("damage_type") or "").lower() == "force", action
    hl = (spell.get("higher_level") or "").lower()
    assert "1d8" in hl and "two slot levels" in hl, spell.get("higher_level")


async def test_base_cast_rolls_a_single_d8(gm_client, gm_ws, roster):
    """At the base 2nd-level slot a hit rolls a single d8: damage_rolled
    lands in [1 + mod, 8 + mod] force."""
    caster = roster[_CASTER]
    mod = _spc_mod(await _sheet(gm_client, caster["id"]))
    try:
        data = await _hit_damage_at(gm_client, caster, "tok_sw_base", 2)
        assert data is not None, "no seed produced a hit at slot 2 — check attack math"
        assert data["damage_type"] == "force", data
        assert data["slot_level"] == 2, data
        assert 1 + mod <= int(data["damage_rolled"]) <= 8 + mod, (
            f"base cast should roll 1d8+{mod} ({1 + mod}..{8 + mod}); got {data['damage_rolled']}"
        )
    finally:
        await _clear_concentration(gm_client, caster["id"])


async def test_upcast_adds_a_die_per_two_levels(gm_client, gm_ws, roster):
    """Cast at a 4th-level slot (+1d8 per two levels above 2nd → 2d8) →
    a hit can roll above 8 + mod, which a single d8 can never reach —
    proving the upcast tier added a second die. Seeds until such a hit
    appears."""
    caster = roster[_CASTER]
    mod = _spc_mod(await _sheet(gm_client, caster["id"]))
    ceiling_for_one_die = 8 + mod
    try:
        found = None
        for seed in range(1, 90):
            await _seed_dice(gm_client, seed)
            await _seed_battle(gm_client, caster, "tok_sw_up")
            r = await _cast(gm_client, caster["id"], 4, "tok_sw_up")
            assert r.status_code == 200, r.text
            data = r.json()
            await _dismiss(gm_client, data["combatant"]["id"])
            assert data["slot_level"] == 4, data
            if data.get("hit") and int(data["damage_rolled"]) > ceiling_for_one_die:
                found = data
                break
        assert found is not None, (
            f"no 4th-level hit exceeded a single d8's ceiling ({ceiling_for_one_die}); "
            "the upcast tier did not add a second die"
        )
        assert found["damage_type"] == "force", found
        assert int(found["damage_rolled"]) <= 16 + mod, (
            f"2d8+{mod} caps at {16 + mod}; got {found['damage_rolled']}"
        )
    finally:
        await _clear_concentration(gm_client, caster["id"])


async def test_cast_binds_concentration_despite_catalog_flag(gm_client, gm_ws, roster):
    """House-rule divergence: the catalog flags Spiritual Weapon
    ``concentration: false`` (RAW it needs no concentration), but the
    runtime binds the weapon to the caster's concentration — the cast
    broadcasts a ``concentration_update`` for "Spiritual Weapon" and the
    weapon combatant comes back ``concentration_bound: true``."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    assert by_slug[_SLUG].get("concentration") is False, (
        "catalog flag changed — this divergence gate assumes RAW concentration: false"
    )
    caster = roster[_CASTER]
    await _seed_battle(gm_client, caster, "tok_sw_conc_t")

    gm_ws.mark()
    r = await _cast(gm_client, caster["id"], 2)
    assert r.status_code == 200, r.text
    weapon = r.json()["combatant"]
    try:
        assert weapon["concentration_bound"] is True, weapon
        cu = await gm_ws.wait_for("concentration_update", timeout=2.0)
        assert cu["data"]["character_id"] == caster["id"], cu
        assert cu["data"]["spell_name"] == "Spiritual Weapon", cu
        assert cu["data"]["ended"] is False, cu
    finally:
        await _dismiss(gm_client, weapon["id"])
        await _clear_concentration(gm_client, caster["id"])
