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
``/attack``) is Phase 1b — out of scope here.

Demo fixture: Garrik Ironside (Fighter, base STR 18 → mod +4) carries an
equipped + attuned Belt of Giant Strength (Hill, STR 21 → mod +5). So:
  - effective STR 21, modifier +5, carry capacity 21 × 15 = 315 lb
    (vs. the base 18 × 15 = 270 lb).
  - STR saves + Athletics gain the +1 modifier delta on top of the
    Stone of Good Luck's existing +1 (the two substrates compose).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BELT_SLUG = "belt-of-giant-strength"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def garrik(roster):
    return roster["Garrik Ironside"]


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
