"""v2.362.0 — magic-items: Berserker Axe (RAW DMG p.155, rare,
attunement, cursed). Bucket-C passive on the NEW
`hp_max_bonus_per_level` substrate: while attuned the wielder's
character-level × N is added to the effective max HP. Folded into
`_effective_max_hp_for_sheet` so it composes with any Amulet-of-Health
CON-mod delta, surfaces on /sheet-json derived (`effective_max_hp`),
AND raises `_sheet_heal_ceiling` so combat heals + long rest + Second
Wind clamp to the boosted pool.

Demo fixture: Krieger Stonefist (Half-Orc Barbarian Lv 7, HP 75/75)
carries the axe as inert Armory's Remainder loot. The harness PATCHes
inventory equipped+attuned and reads /sheet-json. With +1 HP/level ×
level 7 = +7, the effective max HP is 75 + 7 = 82. **v1 simplifications
(GM-narrated):** the cursed berserk save ("on taking damage, DC 15 WIS
or go berserk and attack the nearest creature") needs a damage-pipeline
`on_damage_save` hook + berserk-AI auto-attack neither of which is in
v1; filed for a follow-up. The "can't voluntarily un-attune" cursed
clause is GM-narrated.

Tests:
  - Axe equipped+attuned → /sheet-json `derived.effective_max_hp`
    reports {base: 75, effective: 82, delta: 7, level: 7,
    sources: ["Berserker Axe"]}.
  - Axe inert (default seed) → no `effective_max_hp` key on derived.
  - Axe equipped-but-unattuned → no `effective_max_hp` (attunement
    gate).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


_SLUG = "berserker-axe"


async def _sheet_json(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return r.json() or {}


async def _snapshot_inv(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_inv(gm_client, char_id, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, "Krieger has no berserker-axe inventory item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore_inv(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


@pytest_asyncio.fixture
async def krieger(roster):
    return roster["Krieger Stonefist"]


async def test_berserker_axe_raises_effective_max_hp(gm_client, krieger):
    """Equipped+attuned → /sheet-json derived.effective_max_hp reports
    +1 HP × level 7 = +7 over the stored max."""
    snap = await _patch_inv(
        gm_client, krieger["id"], equipped=True, attuned=True,
    )
    try:
        data = await _sheet_json(gm_client, krieger["id"])
        derived = data.get("derived") or {}
        stored_max = ((data.get("sheet") or {}).get("hp") or {}).get("max")
        emh = derived.get("effective_max_hp") or {}
        assert emh, f"expected effective_max_hp, got: {derived!r}"
        assert int(emh.get("level") or 0) == 7
        assert int(emh.get("delta") or 0) == 7, (
            f"expected +7 (Berserker Axe +1 × level 7), got: {emh!r}"
        )
        assert int(emh.get("base") or 0) == stored_max
        assert int(emh.get("effective") or 0) == int(stored_max) + 7
        sources = list(emh.get("sources") or [])
        assert "Berserker Axe" in sources, (
            f"expected Berserker Axe in sources; got: {sources!r}"
        )
    finally:
        await _restore_inv(gm_client, krieger["id"], snap)


async def test_berserker_axe_inert_baseline(gm_client, krieger):
    """Default seed (axe inert / equipped=False, attuned=False) → no
    effective_max_hp key. Proves the +7 is axe-sourced, not baked."""
    data = await _sheet_json(gm_client, krieger["id"])
    derived = data.get("derived") or {}
    assert derived.get("effective_max_hp") is None, (
        f"expected no effective_max_hp at baseline; got: "
        f"{derived.get('effective_max_hp')!r}"
    )


async def test_berserker_axe_requires_attunement(gm_client, krieger):
    """Equipped but not attuned → no effective_max_hp (attunement
    gate). RAW: 'while you are attuned to this axe, your hit point
    maximum increases by 1 for each of your levels.'"""
    snap = await _patch_inv(
        gm_client, krieger["id"], equipped=True, attuned=False,
    )
    try:
        data = await _sheet_json(gm_client, krieger["id"])
        derived = data.get("derived") or {}
        assert derived.get("effective_max_hp") is None, (
            f"expected no effective_max_hp without attunement; got: "
            f"{derived.get('effective_max_hp')!r}"
        )
    finally:
        await _restore_inv(gm_client, krieger["id"], snap)
