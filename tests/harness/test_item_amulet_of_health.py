"""v2.216.0 — ability-score override engine Phase 3: Amulet of Health
(RAW DMG p.150, rare, attunement). While worn, your Constitution score
*becomes* 19 if it isn't already higher (RAW max(base, set)) — and the
CON change retroactively adjusts max HP. See docs/plans/str-override.md.

The amulet reuses the same `ability_set` substrate as the Belt of Giant
Strength (Phase 1), but on CON instead of STR, plus a second-order
max-HP effect:
  - ``/sheet-json`` ``derived.effective_abilities.CON`` (base/effective/
    modifier) — the override surface, shared with the belt.
  - ``/sheet-json`` ``derived.effective_max_hp`` — the new Phase 3 field:
    the CON-modifier delta × character level added to the stored max HP.
    Display-derived (the stored ``hp.max`` is left untouched in v1).
  - ``/roll`` CON saves pick up the modifier delta (mod(effective) −
    mod(base)) with a breakdown attribution.

Demo fixture: Brother Tavik Stonebrow (Cleric Lv 8, base CON 14 → mod +2,
stored max HP 67) carries an equipped + attuned Amulet of Health — his
3rd attuned item (after the Ring of Protection + Staff of Healing). So:
  - effective CON 19, modifier +4.
  - effective max HP 67 + (+2 mod delta × 8 levels) = 83.
  - CON saves gain the +2 modifier delta.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_AMULET_SLUG = "amulet-of-health"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def tavik(roster):
    return roster["Brother Tavik Stonebrow"]


async def test_amulet_exposes_effective_con_on_sheet_json(gm_client, tavik):
    """``derived.effective_abilities.CON`` reports base 14, effective 19,
    modifier +4 while the amulet is worn."""
    data = await _sheet_json(gm_client, tavik["id"])
    eff = (data.get("derived") or {}).get("effective_abilities") or {}
    assert "CON" in eff, f"expected a CON override entry, got: {eff!r}"
    assert eff["CON"]["base"] == 14
    assert eff["CON"]["effective"] == 19
    assert eff["CON"]["modifier"] == 4


async def test_amulet_raises_effective_max_hp(gm_client, tavik):
    """The second-order effect: ``derived.effective_max_hp`` adds the CON
    modifier delta (+2) × level (8) = +16 to the stored max HP. The stored
    ``hp.max`` itself is left untouched (display-derived in v1)."""
    data = await _sheet_json(gm_client, tavik["id"])
    derived = data.get("derived") or {}
    stored_max = ((data.get("sheet") or {}).get("hp") or {}).get("max")
    emh = derived.get("effective_max_hp") or {}
    assert emh, f"expected effective_max_hp, got: {derived!r}"
    assert emh["level"] == 8
    assert emh["delta"] == 16, (
        f"expected +16 (CON mod delta +2 × level 8), got: {emh!r}"
    )
    assert emh["base"] == stored_max, (
        "effective_max_hp.base should mirror the untouched stored hp.max"
    )
    assert emh["effective"] == stored_max + 16


async def test_amulet_adds_con_save_override_delta(gm_client, tavik):
    """A ``con_save`` roll picks up the amulet's +2 modifier delta with a
    source attribution in the breakdown."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+2",
            "stat_key": "con_save",
            "character_id": tavik["id"],
            "note": "CON save (amulet test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "Amulet of Health" in breakdown, (
        f"expected amulet attribution in save breakdown, got: {breakdown!r}"
    )


async def test_amulet_unequip_reverts_override(gm_client, tavik):
    """Unequipping the amulet reverts both the CON override and the
    effective max-HP boost. Restores the original inventory on teardown."""
    data = await _sheet_json(gm_client, tavik["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    amulet_idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _AMULET_SLUG),
        None,
    )
    assert amulet_idx is not None, "Tavik has no amulet-of-health item"
    try:
        inv[amulet_idx] = {**inv[amulet_idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, tavik["id"])
        derived2 = data2.get("derived") or {}
        eff2 = derived2.get("effective_abilities") or {}
        assert "CON" not in eff2, (
            f"expected no CON override after unequip, got: {eff2!r}"
        )
        assert derived2.get("effective_max_hp") is None, (
            "expected no effective_max_hp after unequip"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
