"""v2.224.0 — capped-additive ability-bonus engine drop-in: Ioun Stone of
Intellect (RAW DMG p.176, very rare, attunement). While orbiting your head it
*increases* your Intelligence by 2, "to a maximum of 20" — a capped ADD,
distinct from the Headband of Intellect's set-to-19. This is the first item to
exercise the new `ability_bonus` / `ability_bonus_cap` substrate
(docs/plans/str-override.md): the bonus composes AFTER any `ability_set`,
raising the score toward its cap but never lowering it.

Surfaces exercised:
  - ``/sheet-json`` ``derived.effective_abilities.INT`` (base/effective/
    modifier) — the override surface, shared with the set-based items but
    here driven by the additive bonus.
  - ``/roll`` INT saves pick up the modifier delta (mod(effective) −
    mod(base)) with a source attribution.
  - The RAW "+to a maximum of 20" cap: patching INT to 19 yields effective
    20 (only +1 of the +2 applied), restored on teardown.

Demo fixture: Magnus Hexbinder (Warlock, base INT 10 → mod 0) wears an
equipped + attuned Ioun Stone of Intellect — his 3rd attuned item (after the
Wand of Fear + Wand of Paralysis, RAW max 3). So effective INT 12, modifier
+1 (a clean +1 delta with no set to confound it).
"""
import pytest
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_IOUN_SLUG = "ioun-stone"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def magnus(roster):
    return roster["Magnus Hexbinder"]


async def test_ioun_stone_exposes_effective_int_on_sheet_json(gm_client, magnus):
    """``derived.effective_abilities.INT`` reports base 10, effective 12,
    modifier +1 — a pure additive +2 bonus (well under the cap)."""
    data = await _sheet_json(gm_client, magnus["id"])
    eff = (data.get("derived") or {}).get("effective_abilities") or {}
    assert "INT" in eff, f"expected an INT override entry, got: {eff!r}"
    assert eff["INT"]["base"] == 10
    assert eff["INT"]["effective"] == 12
    assert eff["INT"]["modifier"] == 1
    assert "Ioun Stone" in str(eff["INT"]["source"]), eff["INT"]


async def test_ioun_stone_adds_int_save_override_delta(gm_client, magnus):
    """An ``int_save`` roll picks up the stone's +1 modifier delta with a
    source attribution in the breakdown."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+0",
            "stat_key": "int_save",
            "character_id": magnus["id"],
            "note": "INT save (ioun stone test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "+1" in breakdown and "Ioun Stone" in breakdown, (
        f"expected +1 ioun-stone delta in save breakdown, got: {breakdown!r}"
    )


async def test_ioun_stone_caps_at_20(gm_client, magnus):
    """RAW "to a maximum of 20": with INT temporarily set to 19, the +2 only
    raises the effective score to 20 (a +1 net, not +2). Restores the
    original abilities on teardown."""
    data = await _sheet_json(gm_client, magnus["id"])
    abilities = dict((data.get("sheet") or {}).get("abilities") or {})
    snapshot = dict(abilities)
    try:
        abilities["INT"] = 19
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"abilities": abilities},
        )
        data2 = await _sheet_json(gm_client, magnus["id"])
        eff2 = (data2.get("derived") or {}).get("effective_abilities") or {}
        assert "INT" in eff2, f"expected an INT override entry, got: {eff2!r}"
        assert eff2["INT"]["base"] == 19
        assert eff2["INT"]["effective"] == 20, (
            f"expected the +2 to clamp at 20, got: {eff2['INT']!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"abilities": snapshot},
        )


# v2.225.0 — the remaining five Ioun ability variants, each seeded on a demo
# PC with a free attunement slot whose bumped ability is mechanically inert to
# existing assertions (dump stat / heavy-armor DEX / secondary stat). Every one
# is a pure-additive read (base well under the 20 cap), proving the single
# `ioun-stone` slug + per-item `_ability_bonus` covers all six ability variants.
# v2.245.0 — the Lyra "STR" variant was dropped here: her Ioun Stone of
# Strength was detuned (kept equipped) in the demo seed to free her 3rd
# attunement slot for the Ring of Mind Shielding. STR-via-ioun is the most
# redundant ability demo (STR also rides the three Belts of Giant Strength +
# Gauntlets of Ogre Power), so its loss costs the least coverage.
# v2.246.0 — the Brakka "CON" variant was dropped likewise: her Ioun Stone of
# Constitution was detuned (kept equipped) to free her 3rd attunement slot for
# the Ring of Warmth. CON-via-ioun is the next-most-redundant ability demo —
# the Amulet of Health (Tavik) still covers the CON `ability_bonus` /
# effective-max-HP surface (test_item_amulet_of_health.py), so this loses no
# net coverage.
# v2.247.0 — the Rowan "CHA" variant was dropped likewise: his Ioun Stone of
# Charisma was detuned (kept equipped) to free his 3rd attunement slot for the
# Boots of the Winterlands. CHA-via-ioun was a dump-stat demo on a ranger.
# v2.248.0 — the Caelan "DEX" variant was dropped likewise: his Ioun Stone of
# Dexterity was detuned (kept equipped) to free his 3rd attunement slot for the
# Armor of Resistance (Acid). DEX-via-ioun was the lowest-value drop — Caelan
# wears heavy armor, so the DEX bump never touched his AC. The remaining WIS row
# + the INT primary test still prove the single `ioun-stone` slug + per-item
# `_ability_bonus` covers the ability variants.
_VARIANTS = [
    ("Krieger Stonefist", "WIS", 13, 15, 2),
]


@pytest.mark.parametrize("name,ability,base,effective,modifier", _VARIANTS)
async def test_ioun_variant_exposes_effective_ability(
    gm_client, roster, name, ability, base, effective, modifier
):
    """Each remaining Ioun ability variant raises its PC's score by the
    additive +2 (pure, under the cap) and reports it on `/sheet-json`."""
    char = roster[name]
    data = await _sheet_json(gm_client, char["id"])
    eff = (data.get("derived") or {}).get("effective_abilities") or {}
    assert ability in eff, f"{name}: expected {ability} override, got {eff!r}"
    assert eff[ability]["base"] == base
    assert eff[ability]["effective"] == effective
    assert eff[ability]["modifier"] == modifier
    assert "Ioun Stone" in str(eff[ability]["source"]), eff[ability]


async def test_ioun_stone_unequip_reverts_bonus(gm_client, magnus):
    """Unequipping the stone reverts the INT bonus. Restores the original
    inventory on teardown."""
    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _IOUN_SLUG),
        None,
    )
    assert idx is not None, "Magnus has no ioun-stone item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, magnus["id"])
        eff2 = (data2.get("derived") or {}).get("effective_abilities") or {}
        assert "INT" not in eff2, (
            f"expected no INT override after unequip, got: {eff2!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
