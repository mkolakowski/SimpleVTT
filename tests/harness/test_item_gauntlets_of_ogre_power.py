"""v2.219.0 — ability-score override engine drop-in: Gauntlets of Ogre
Power (RAW DMG p.171, uncommon, attunement). While worn, your Strength
score *becomes* 19 if it isn't already higher (RAW max(base, set)). A pure
data drop-in on the completed override substrate (docs/plans/str-override.md):
same `ability_set` mechanism as the Belt of Giant Strength (STR), Amulet of
Health (CON), and Headband of Intellect (INT).

Surfaces exercised:
  - ``/sheet-json`` ``derived.effective_abilities.STR`` (base/effective/
    modifier) — the override surface, shared with the belt.
  - ``/sheet-json`` ``derived.carry.carry_capacity_lb`` — STR × 15, so the
    boosted STR raises the carry meter.
  - ``/roll`` STR saves + STR-based ability/skill checks pick up the
    modifier delta (mod(effective) − mod(base)) with a source attribution.

Demo fixture: Rowan Quickbow (Ranger, base STR 12 → mod +1, 180 lb cap)
wears equipped + attuned Gauntlets of Ogre Power — his 1st attuned item
(RAW max 3). So effective STR 19, modifier +4 (a +3 delta), carry 285 lb.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_GAUNTLETS_SLUG = "gauntlets-of-ogre-power"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def rowan(roster):
    return roster["Rowan Quickbow"]


async def test_gauntlets_expose_effective_str_on_sheet_json(gm_client, rowan):
    """``derived.effective_abilities.STR`` reports base 12, effective 19,
    modifier +4 while the gauntlets are worn."""
    data = await _sheet_json(gm_client, rowan["id"])
    eff = (data.get("derived") or {}).get("effective_abilities") or {}
    assert "STR" in eff, f"expected a STR override entry, got: {eff!r}"
    assert eff["STR"]["base"] == 12
    assert eff["STR"]["effective"] == 19
    assert eff["STR"]["modifier"] == 4
    assert "Gauntlets of Ogre Power" in str(eff["STR"]["source"]), eff["STR"]


async def test_gauntlets_raise_carry_capacity(gm_client, rowan):
    """The boosted STR flows into carry capacity: 19 × 15 = 285 lb (up
    from the base 12 × 15 = 180 lb)."""
    data = await _sheet_json(gm_client, rowan["id"])
    cap = ((data.get("derived") or {}).get("carry") or {}).get(
        "carry_capacity_lb"
    )
    assert cap == 285, f"expected boosted cap 285, got {cap!r}"


async def test_gauntlets_add_str_save_override_delta(gm_client, rowan):
    """A ``str_save`` roll picks up the gauntlets' +3 modifier delta (mod
    +4 − base mod +1) with a source attribution in the breakdown."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+1",
            "stat_key": "str_save",
            "character_id": rowan["id"],
            "note": "STR save (gauntlets test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "+3" in breakdown and "Gauntlets of Ogre Power" in breakdown, (
        f"expected +3 gauntlets delta in save breakdown, got: {breakdown!r}"
    )


async def test_gauntlets_unequip_reverts_override(gm_client, rowan):
    """Unequipping the gauntlets reverts the STR override. Restores the
    original inventory on teardown."""
    data = await _sheet_json(gm_client, rowan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _GAUNTLETS_SLUG),
        None,
    )
    assert idx is not None, "Rowan has no gauntlets-of-ogre-power item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, rowan["id"])
        eff2 = (data2.get("derived") or {}).get("effective_abilities") or {}
        assert "STR" not in eff2, (
            f"expected no STR override after unequip, got: {eff2!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
