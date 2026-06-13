"""v2.212.0 — ability-score override engine Phase 1: Belt of Giant
Strength (RAW DMG p.155, rare, attunement). While worn, your Strength
score *becomes* the belt's value — but only if higher (RAW max(base,
set)). See docs/plans/str-override.md.

The override flows to three read sites this commit wires:
  - ``/sheet-json`` ``derived.effective_abilities.STR`` (base/effective/
    modifier) — only present when an item overrides the score.
  - ``/sheet-json`` ``derived.carry.carry_capacity_lb`` — carry capacity
    uses the effective STR (Belt of Giant Strength is read site #4 of
    the carrying-capacity engine, v2.159.27).
  - ``/roll`` STR saves + STR-based checks pick up the MODIFIER delta
    (mod(effective) − mod(base)) with a breakdown attribution.

Weapon attack/damage (baked into the sheet's stored attack entries via
``/attack``) is Phase 1b (v2.213.0): the belt's +1 effective-STR modifier
delta flows into Garrik's Greatsword (a STR weapon) to-hit roll AND damage
expression. DEX-keyed attacks (bows / finesse) are untouched by the
STR-setting belt.

Demo fixture: Garrik Ironside (Fighter, base STR 18 → mod +4) carries an
equipped + attuned Belt of Giant Strength (Hill, STR 21 → mod +5). So:
  - effective STR 21, modifier +5, carry capacity 21 × 15 = 315 lb
    (vs. the base 18 × 15 = 270 lb).
  - STR saves + Athletics gain the +1 modifier delta on top of the
    Stone of Good Luck's existing +1 (the two substrates compose).
"""
import re

import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BELT_SLUG = "belt-of-giant-strength"


def _attack_flat_bonus(data):
    """Extract the flat to-hit bonus from an /attack response: the d20
    rolled value is in the breakdown (``1d20[N]=N``), so the flat bonus is
    ``attack_total − N``. Garrik has no roll_state / buffs, so the d20 is a
    single die."""
    m = re.search(r"1d20\[(\d+)\]=\d+", data["attack_breakdown"])
    assert m, f"unexpected attack_breakdown shape: {data['attack_breakdown']!r}"
    return data["attack_total"] - int(m.group(1))


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def garrik(roster):
    return roster["Garrik Ironside"]


@pytest_asyncio.fixture
async def zara(roster):
    return roster["Zara Emberfire"]


@pytest_asyncio.fixture
async def brakka(roster):
    return roster["Brakka Wildmane"]


async def test_belt_exposes_effective_str_on_sheet_json(gm_client, garrik):
    """The override surface: ``derived.effective_abilities.STR`` reports
    base 18, effective 21, modifier +5 while the belt is worn."""
    data = await _sheet_json(gm_client, garrik["id"])
    eff = (data.get("derived") or {}).get("effective_abilities") or {}
    assert "STR" in eff, (
        f"expected an STR override entry, got: {eff!r}"
    )
    assert eff["STR"]["base"] == 18
    assert eff["STR"]["effective"] == 21
    assert eff["STR"]["modifier"] == 5


async def test_belt_raises_carry_capacity(gm_client, garrik):
    """Carry capacity uses the effective STR: 21 × 15 = 315 lb, not the
    base 18 × 15 = 270 lb."""
    data = await _sheet_json(gm_client, garrik["id"])
    carry = (data.get("derived") or {}).get("carry") or {}
    assert carry.get("carry_capacity_lb") == 315, (
        f"expected carry capacity 315 (STR 21 × 15), got: {carry!r}"
    )


async def test_belt_adds_str_save_override_delta(gm_client, garrik):
    """A ``str_save`` roll picks up the belt's +1 modifier delta with a
    source attribution in the breakdown."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+8",
            "stat_key": "str_save",
            "character_id": garrik["id"],
            "note": "STR save (belt test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "Belt of Giant Strength" in breakdown, (
        f"expected belt attribution in save breakdown, got: {breakdown!r}"
    )


async def test_belt_adds_athletics_override_delta(gm_client, garrik):
    """An Athletics (STR skill) roll picks up the belt's +1 modifier
    delta — skill rolls carry ``stat_ability`` rather than a ``*_check``
    stat_key."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+8",
            "stat_key": "Athletics",
            "stat_ability": "STR",
            "character_id": garrik["id"],
            "note": "Athletics (belt test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "Belt of Giant Strength" in breakdown, (
        f"expected belt attribution in skill breakdown, got: {breakdown!r}"
    )


async def test_belt_unequip_reverts_override(gm_client, garrik):
    """Unequipping the belt reverts the override: STR drops out of
    ``effective_abilities`` and carry capacity returns to the base
    18 × 15 = 270 lb. Restores the original inventory on teardown."""
    data = await _sheet_json(gm_client, garrik["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    belt_idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _BELT_SLUG),
        None,
    )
    assert belt_idx is not None, "Garrik has no belt-of-giant-strength item"
    try:
        inv[belt_idx] = {**inv[belt_idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, garrik["id"])
        derived2 = data2.get("derived") or {}
        eff2 = derived2.get("effective_abilities") or {}
        assert "STR" not in eff2, (
            f"expected no STR override after unequip, got: {eff2!r}"
        )
        assert (derived2.get("carry") or {}).get("carry_capacity_lb") == 270, (
            "expected carry capacity 270 (base STR 18 × 15) after unequip"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_belt_tier_override_sets_higher_str(gm_client, zara):
    """Phase 2b (v2.215.0): the SRD ships a single `belt-of-giant-strength`
    slug whose catalog default is the Hill tier (STR 21). A per-item
    `_ability_set` override rides the inventory item and WINS over that
    default. Zara Emberfire (Sorcerer, base STR 8 → mod -1) wears a Belt of
    Stone Giant Strength flagged `_ability_set: {"STR": 23}`, so her
    effective STR is 23 (mod +6) — NOT the catalog default 21."""
    data = await _sheet_json(gm_client, zara["id"])
    eff = (data.get("derived") or {}).get("effective_abilities") or {}
    assert "STR" in eff, f"expected an STR override entry, got: {eff!r}"
    assert eff["STR"]["base"] == 8
    assert eff["STR"]["effective"] == 23, (
        "expected the per-item tier override (23) to beat the catalog "
        f"default (21), got: {eff['STR']!r}"
    )
    assert eff["STR"]["modifier"] == 6


async def test_belt_tier_override_raises_carry_capacity(gm_client, zara):
    """The Stone-tier override flows to carry capacity: 23 × 15 = 345 lb,
    not the base 8 × 15 = 120 lb nor the Hill-default 21 × 15 = 315 lb."""
    data = await _sheet_json(gm_client, zara["id"])
    carry = (data.get("derived") or {}).get("carry") or {}
    assert carry.get("carry_capacity_lb") == 345, (
        f"expected carry capacity 345 (STR 23 × 15), got: {carry!r}"
    )


async def test_belt_storm_tier_sets_str_29(gm_client, brakka):
    """Phase 2c (v2.223.0): the legendary top tier. Brakka Wildmane
    (Barbarian, base STR 17 → mod +3) wears a Belt of Storm Giant Strength
    flagged `_ability_set: {"STR": 29}`, so her effective STR is 29 (mod +9)
    — the catalog default (21) and the Stone tier (23) are both beaten by the
    per-item override. The +12 swing is the largest in the demo."""
    data = await _sheet_json(gm_client, brakka["id"])
    eff = (data.get("derived") or {}).get("effective_abilities") or {}
    assert "STR" in eff, f"expected an STR override entry, got: {eff!r}"
    assert eff["STR"]["base"] == 17
    assert eff["STR"]["effective"] == 29, (
        "expected the Storm-tier override (29) to beat the catalog default "
        f"(21), got: {eff['STR']!r}"
    )
    assert eff["STR"]["modifier"] == 9


async def test_belt_storm_tier_raises_carry_capacity(gm_client, brakka):
    """The Storm-tier override flows to carry capacity: 29 × 15 = 435 lb,
    not the base 17 × 15 = 255 lb."""
    data = await _sheet_json(gm_client, brakka["id"])
    carry = (data.get("derived") or {}).get("carry") or {}
    assert carry.get("carry_capacity_lb") == 435, (
        f"expected carry capacity 435 (STR 29 × 15), got: {carry!r}"
    )


async def test_belt_boosts_weapon_attack_and_damage(gm_client, gm_ws, garrik):
    """Phase 1b: the belt's +1 effective-STR modifier delta flows into
    Garrik's Greatsword (a STR weapon, attack_index 0, baked +8 = STR +4 +
    PB +4). The to-hit flat bonus reads +9 and the damage expression carries
    the +1 (``2d6+4`` → ``2d6+4+1``). ``damage_expr`` rides on the
    ``weapon_attack`` broadcast."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": garrik["id"], "attack_index": 0, "override": True},
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("weapon_attack")
    data = msg["data"]
    assert data["attack_name"] == "Greatsword"
    assert data["damage_expr"] == "2d6+4+1", (
        f"expected belt +1 appended to damage expr, got {data['damage_expr']!r}"
    )
    assert _attack_flat_bonus(data) == 9, (
        "expected effective to-hit flat +9 (base +8 + belt +1), got "
        f"{_attack_flat_bonus(data)}"
    )


async def test_belt_weapon_boost_reverts_on_unequip(gm_client, gm_ws, garrik):
    """Unequipping the belt reverts the weapon boost: the Greatsword's
    damage expression drops back to ``2d6+4`` and the to-hit flat to +8.
    Restores the original inventory on teardown."""
    data = await _sheet_json(gm_client, garrik["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    belt_idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _BELT_SLUG),
        None,
    )
    assert belt_idx is not None, "Garrik has no belt-of-giant-strength item"
    try:
        inv[belt_idx] = {**inv[belt_idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inv},
        )
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": garrik["id"], "attack_index": 0,
                  "override": True},
        )
        assert resp.status_code == 200, resp.text
        msg = await gm_ws.wait_for("weapon_attack")
        data2 = msg["data"]
        assert data2["damage_expr"] == "2d6+4", (
            f"expected base damage expr after unequip, got {data2['damage_expr']!r}"
        )
        assert _attack_flat_bonus(data2) == 8, (
            "expected base to-hit flat +8 after unequip, got "
            f"{_attack_flat_bonus(data2)}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
