"""v2.291.0 — Spellguard Shield (RAW DMG p.201, very rare, attunement).

RAW: "while holding this shield, you have advantage on saving throws against
spells and other magical effects, and spell attacks have disadvantage against
you." The clean passive half rides the v2.236.0 `spell_save_advantage`
substrate (the same boolean-OR field the Mantle of Spell Resistance uses): the
`spellguard-shield` payload carries `spell_save_advantage: True`, aggregates in
`_equipped_item_effects`, and surfaces on `/sheet-json` as
`derived.spell_save_advantage = {sources}`. The advantage is descriptive in v1;
the spell-attack-disadvantage half is GM-narrated.

Demo fixture: Caelan (Devotion Paladin) carries the shield as inert spare loot
(equipped=False) so it doesn't replace his plain Shield (+2 AC) or change his
attuned count. The tests PATCH it equipped+attuned, read the projection, then
restore the seed inventory.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SHIELD_SLUG = "spellguard-shield"


@pytest_asyncio.fixture
async def caelan(roster):
    return next(
        v for k, v in roster.items() if "Caelan" in k
    )


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _equip_and_read_derived(gm_client, char_id):
    """PATCH the spare shield ON (equipped+attuned), read /sheet-json, then
    restore the original inventory. Returns the post-equip derived block."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _SHIELD_SLUG:
            it["equipped"] = True
            it["attuned"] = True
            found = True
    assert found, "Caelan has no spellguard-shield item"
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    try:
        data2 = await _sheet_json(gm_client, char_id)
        return data2.get("derived") or {}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_shield_grants_spell_save_advantage(gm_client, caelan):
    """Happy path: equipping+attuning the shield surfaces
    `derived.spell_save_advantage` with the shield named in sources."""
    derived = await _equip_and_read_derived(gm_client, caelan["id"])
    ssa = derived.get("spell_save_advantage")
    assert ssa is not None, (
        f"expected derived.spell_save_advantage, got: {derived!r}"
    )
    assert any(
        "Spellguard Shield" in str(s) for s in ssa.get("sources") or []
    ), f"expected the shield named in sources, got: {ssa!r}"


async def test_shield_requires_attunement(gm_client, caelan):
    """The shield is an attunement item — equipped-but-unattuned yields no
    `spell_save_advantage`. Restores the original inventory on teardown."""
    char_id = caelan["id"]
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _SHIELD_SLUG:
            it["equipped"] = True
            it["attuned"] = False
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    try:
        derived = (await _sheet_json(gm_client, char_id)).get("derived") or {}
        ssa = derived.get("spell_save_advantage") or {}
        assert not any(
            "Spellguard Shield" in str(s) for s in ssa.get("sources") or []
        ), f"unattuned shield wrongly granted the advantage, got: {ssa!r}"
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_shield_baseline_has_no_advantage(gm_client, caelan):
    """Control: with the shield inert (seed, equipped=False), Caelan has no
    spellguard-sourced spell-save advantage — proving it's shield-sourced."""
    data = await _sheet_json(gm_client, caelan["id"])
    ssa = (data.get("derived") or {}).get("spell_save_advantage") or {}
    assert not any(
        "Spellguard Shield" in str(s) for s in ssa.get("sources") or []
    ), f"unexpected baseline spellguard advantage, got: {ssa!r}"
