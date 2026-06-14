"""v2.265.0 — charged-items Phase 5: Wand of the War Mage, +1/+2/+3 (RAW
DMG p.211, uncommon–rare, attunement): while holding the wand the wielder
gains a bonus to spell attack rolls (and ignores half cover on a spell
attack). A passive — no charges — modeled as a summed, attunement-gated
`spell_attack_bonus` int in `_equipped_item_effects`, surfaced on
`/sheet-json` as `derived.spell_attack_bonus = {bonus, sources}`, and
folded into the caster's spell attack bonus at cast-resolution time. The
single SRD slug defaults to +1; the +2/+3 tiers ride the item via a
per-item `_spell_attack_bonus` rider (the Ioun Stone tier pattern). The
ignore-half-cover clause is GM-narrated in v1.

Demo fixture: Magnus Hexbinder (Fiend Warlock — the demo's blaster) wears
the +2 wand attuned. His Eldritch Blast (spell attack, index 0) gains the
+2 to hit. The wand is his 5th attuned item (seed-load bypasses the RAW
3-item cap, enforced at /attune runtime only); the attunement guard
detunes via PATCH sheet-fields (cap-bypassing) so the restore can't trip
the cap.

Tests:
  - derived read: /sheet-json reports derived.spell_attack_bonus +2.
  - detune gate: un-attuning (still equipped) drops the derived read.
  - unequip gate: unequipping drops the derived read.
  - end-to-end: an Eldritch Blast attack roll carries +2 more flat
    to-hit modifier attuned vs detuned (delta == 2).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_WAND_SLUG = "wand-of-the-war-mage"
_ELDRITCH_BLAST_INDEX = 0


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _wand_index(inventory):
    return next(
        (i for i, it in enumerate(inventory)
         if isinstance(it, dict) and it.get("_slug") == _WAND_SLUG),
        None,
    )


def _flat_modifier_sum(breakdown: str) -> int:
    """Sum the flat (non-dice) integer modifier tokens in a roll breakdown.

    Breakdown format is ``<dice>[rolls]=<subtotal> <mod1> ...  =>  <total>``.
    The dice token contains brackets/``=``; the flat modifiers are bare
    signed integers. The d20 face is random but the flat modifier sum is
    deterministic (prof + ability mod + wand), so it's stable across rolls.
    """
    left = (breakdown or "").split("=>")[0].strip()
    total = 0
    for t in left.split():
        if t.lstrip("+-").isdigit():
            total += int(t)
    return total


@pytest_asyncio.fixture
async def magnus(gm_client, roster):
    m = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{m['id']}/rest",
        json={"type": "long"},
    )
    return m


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_war_mage_exposes_derived(gm_client, magnus):
    """Happy path: Magnus's /sheet-json reports derived.spell_attack_bonus
    of +2 with the wand named in its sources."""
    data = await _sheet_json(gm_client, magnus["id"])
    sab = (data.get("derived") or {}).get("spell_attack_bonus")
    assert sab is not None, (
        f"expected derived.spell_attack_bonus, got: {data.get('derived')!r}"
    )
    assert sab.get("bonus") == 2, f"expected +2, got: {sab!r}"
    assert any(
        "War Mage" in str(s) for s in sab.get("sources") or []
    ), f"expected the wand named in sources, got: {sab!r}"


async def test_war_mage_detune_drops_derived(gm_client, magnus):
    """Attunement gate: un-attuning the wand (still equipped) removes
    derived.spell_attack_bonus. Restores inventory on teardown."""
    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = _wand_index(inv)
    assert idx is not None, "Magnus has no Wand of the War Mage"
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, magnus["id"])
        assert "spell_attack_bonus" not in (data2.get("derived") or {}), (
            f"expected no spell_attack_bonus after detune, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_war_mage_unequip_drops_derived(gm_client, magnus):
    """Unequipping the wand removes derived.spell_attack_bonus. Restores
    inventory on teardown."""
    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = _wand_index(inv)
    assert idx is not None, "Magnus has no Wand of the War Mage"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, magnus["id"])
        assert "spell_attack_bonus" not in (data2.get("derived") or {}), (
            f"expected no spell_attack_bonus after unequip, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_war_mage_adds_spell_attack_to_hit(gm_client, magnus):
    """End-to-end: Magnus's Eldritch Blast attack roll carries +2 more
    flat to-hit modifier while the wand is attuned than after detuning.
    Asserts on the flat-modifier delta (stable across random d20 faces).
    Restores inventory on teardown."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit = next((t for t in templates if "bandit" in t["name"].lower()), templates[0])

    async def _cast_breakdown():
        await _seed_battle(gm_client, [
            {"id": f"tok_wm_{magnus['id']}", "char_id": magnus["id"],
             "name": magnus["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": "tok_wm_bandit", "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 7, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": magnus["id"],
                "spell_index": _ELDRITCH_BLAST_INDEX,
                "slot_level": 0,
                "class_slug": "warlock",
                "target_combatant_id": "tok_wm_bandit",
                "target_name": bandit["name"],
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        return resp.json().get("auto_attack_breakdown") or ""

    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = _wand_index(inv)
    assert idx is not None, "Magnus has no Wand of the War Mage"
    try:
        mods_with = _flat_modifier_sum(await _cast_breakdown())

        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": inv},
        )
        mods_without = _flat_modifier_sum(await _cast_breakdown())

        assert mods_with - mods_without == 2, (
            f"expected +2 spell-attack delta from the wand, got "
            f"{mods_with} (attuned) vs {mods_without} (detuned)"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
