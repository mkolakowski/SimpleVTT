"""v2.218.0 — ability-score override engine drop-in: Headband of Intellect
(RAW DMG p.173, uncommon, attunement). While worn, your Intelligence score
*becomes* 19 if it isn't already higher (RAW max(base, set)). A pure data
drop-in on the now-complete override substrate (docs/plans/str-override.md):
same `ability_set` mechanism as the Belt of Giant Strength (STR) and Amulet
of Health (CON), here on INT.

Surfaces exercised:
  - ``/sheet-json`` ``derived.effective_abilities.INT`` (base/effective/
    modifier) — the override surface, shared with the belt + amulet.
  - ``/roll`` INT saves + INT-based ability/skill checks pick up the
    modifier delta (mod(effective) − mod(base)) with a source attribution.

Demo fixture: Mira Greenleaf (Druid, base INT 10 → mod 0) wears an equipped
+ attuned Headband of Intellect — her 2nd attuned item (after the Vorpal
Scimitar, RAW max 3). So effective INT 19, modifier +4 (a clean +4 delta).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_HEADBAND_SLUG = "headband-of-intellect"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def mira(roster):
    return roster["Mira Greenleaf"]


async def test_headband_exposes_effective_int_on_sheet_json(gm_client, mira):
    """``derived.effective_abilities.INT`` reports base 10, effective 19,
    modifier +4 while the headband is worn."""
    data = await _sheet_json(gm_client, mira["id"])
    eff = (data.get("derived") or {}).get("effective_abilities") or {}
    assert "INT" in eff, f"expected an INT override entry, got: {eff!r}"
    assert eff["INT"]["base"] == 10
    assert eff["INT"]["effective"] == 19
    assert eff["INT"]["modifier"] == 4
    assert "Headband of Intellect" in str(eff["INT"]["source"]), eff["INT"]


async def test_headband_adds_int_save_override_delta(gm_client, mira):
    """An ``int_save`` roll picks up the headband's +4 modifier delta with a
    source attribution in the breakdown."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+0",
            "stat_key": "int_save",
            "character_id": mira["id"],
            "note": "INT save (headband test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "+4" in breakdown and "Headband of Intellect" in breakdown, (
        f"expected +4 headband delta in save breakdown, got: {breakdown!r}"
    )


async def test_headband_unequip_reverts_override(gm_client, mira):
    """Unequipping the headband reverts the INT override. Restores the
    original inventory on teardown."""
    data = await _sheet_json(gm_client, mira["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _HEADBAND_SLUG),
        None,
    )
    assert idx is not None, "Mira has no headband-of-intellect item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, mira["id"])
        eff2 = (data2.get("derived") or {}).get("effective_abilities") or {}
        assert "INT" not in eff2, (
            f"expected no INT override after unequip, got: {eff2!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
