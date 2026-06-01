"""v2.99.11 — (D) Phase 2 race-keyed save advantage.

When a PC of a Fey-Ancestry race (Elf / Half-Elf / Wood Elf / High
Elf / Dark Elf) rolls a save vs a spell that installs Charmed, the
d20 rolls with advantage (2d20kh1) instead of 1d20. RAW: "You have
advantage on saving throws against being charmed."

Same kh1 idiom as Danger Sense / Indomitable / Aura of Devotion;
the v2.99.11 helper ``_race_grants_save_advantage`` returns
(applies, trait_slug, trait_name) and the construction-time hook
swaps the base_expression. Companion broadcast
``_broadcast_race_save_advantage`` emits a feature_used event with
source = trait_slug (``fey-ancestry`` / ``gnome-cunning``) so the
roll-log card surfaces the trigger.

Wired into the same three save-roll construction sites as Danger
Sense:
  - ``/cast_spell`` single-target PC save (roll_request)
  - ``/cast_spell`` AoE PC save (roll_request)
  - ``/place_aoe`` PC server-rolled save (expr direct)

Tests:
  - happy: Lyra (Half-Elf Bard) casts Suggestion at Thalindra (Elf
    Wizard) → Wis save → spell condition is Charmed → Fey Ancestry
    fires → base_expression = 2d20kh1 + feature_used(source=
    fey-ancestry) on Thalindra.
  - control non-charm: Lyra casts Hold Person at Thalindra → Wis
    save → spell condition is Paralyzed → Fey Ancestry does NOT
    fire (charm-only) → base_expression stays 1d20.
  - control non-Fey-Ancestry race: Lyra casts Suggestion at Tavik
    (Hill Dwarf Cleric) → Wis save vs Charmed but Tavik is not
    Elf/Half-Elf → base_expression stays 1d20.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Lyra Sunstrider's bard spell list — see app/demo_seed.py
# _bard_sheet. Stable index per the project's harness convention
# (see test_cast_spell_target.py _find_spell_index docstring).
SUGGESTION_LYRA_INDEX = 9   # Wis save → Charmed (L2 Bard)
HOLD_PERSON_LYRA_INDEX = 11  # Wis save → Paralyzed (L2 Bard) — control


@pytest_asyncio.fixture
async def lyra_rested(gm_client, roster):
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    return lyra


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _race_save_broadcasts(gm_ws, character_id: int, trait_slug: str) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == trait_slug
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _roll_request_broadcast(gm_ws):
    msgs = gm_ws.buffered("roll_request")
    return msgs[-1] if msgs else None


def _tok(char):
    """Build a minimal combatant entry for `_seed_battle`."""
    return {
        "id": f"tok_race_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30,
        "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def test_fey_ancestry_advantage_on_charm_save(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Lyra (Half-Elf Bard, Lv 6) casts Suggestion at Thalindra
    (Elf Wizard, Lv 7) → Wis save → Suggestion installs Charmed →
    Fey Ancestry fires → base_expression = 2d20kh1 AND a
    feature_used(source=fey-ancestry) broadcast fires for Thalindra.
    """
    lyra = lyra_rested
    thal = roster["Thalindra Moonwhisper"]
    await _seed_battle(gm_client, [_tok(lyra), _tok(thal)])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": SUGGESTION_LYRA_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": f"tok_race_{thal['id']}",
            "target_character_id": thal["id"],
            "target_name": thal["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "WIS"
    assert data["auto_save_target_kind"] == "pc"
    assert data["auto_save_prompted"] is True

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None, "expected a roll_request broadcast for Thalindra's Wis save"
    assert rr["data"]["base_expression"] == "2d20kh1", (
        f"Fey Ancestry should set base_expression to 2d20kh1; "
        f"got {rr['data']['base_expression']!r}"
    )
    msgs = _race_save_broadcasts(gm_ws, thal["id"], "fey-ancestry")
    assert msgs, (
        f"expected feature_used(source=fey-ancestry) for Thalindra; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_fey_ancestry_skips_non_charm_save(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Control: Hold Person installs Paralyzed (not Charmed). Even
    though Thalindra is an Elf with Fey Ancestry, the trait gates
    on the spell's condition. base_expression stays 1d20.
    """
    lyra = lyra_rested
    thal = roster["Thalindra Moonwhisper"]
    await _seed_battle(gm_client, [_tok(lyra), _tok(thal)])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": HOLD_PERSON_LYRA_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": f"tok_race_{thal['id']}",
            "target_character_id": thal["id"],
            "target_name": thal["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"Hold Person (Paralyzed) should NOT trigger Fey Ancestry; "
        f"got base_expression={rr['data']['base_expression']!r}"
    )
    msgs = _race_save_broadcasts(gm_ws, thal["id"], "fey-ancestry")
    assert not msgs, (
        f"Fey Ancestry broadcast should NOT fire for Paralyzed install: {msgs}"
    )


async def test_fey_ancestry_skips_non_fey_race(
    gm_client, gm_ws, roster, lyra_rested,
):
    """Control: Tavik is a Hill Dwarf (not Elf / Half-Elf) so even
    though Suggestion installs Charmed and the save is Wis,
    Fey Ancestry doesn't fire. base_expression stays 1d20.
    """
    lyra = lyra_rested
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_tok(lyra), _tok(tavik)])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": SUGGESTION_LYRA_INDEX,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": f"tok_race_{tavik['id']}",
            "target_character_id": tavik["id"],
            "target_name": tavik["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"Hill Dwarf has no Fey Ancestry; "
        f"got base_expression={rr['data']['base_expression']!r}"
    )
    msgs = _race_save_broadcasts(gm_ws, tavik["id"], "fey-ancestry")
    assert not msgs, (
        f"Fey Ancestry broadcast should NOT fire for Hill Dwarf: {msgs}"
    )


# v2.99.12 — Dwarven Resilience tests. Thalindra (Elf Wizard, Lv 7)
# casts Poison Spray (cantrip, CON save, poison damage) at Tavik
# (Hill Dwarf Cleric, Lv 8). The v2.99.12 rule entry matches on
# damage_type="poison" OR condition_keys=["poisoned"], so Tavik's
# CON save base_expression swaps `1d20 → 2d20kh1` + a
# `feature_used(source=dwarven-resilience)` broadcast fires.
#
# Poison Spray's slot/level conventions: cantrip, level=0, no
# slot_level required (server ignores). spell_index = last appended
# in v2.99.12 = index 14 on Thalindra's spell list (post-v2.97.72
# Confusion + Banishment).

POISON_SPRAY_THAL_INDEX = 14  # appended last in v2.99.12


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


async def test_dwarven_resilience_advantage_on_poison_save(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Thalindra (Elf Wizard) casts Poison Spray (CON save, 1d12
    poison) at Tavik (Hill Dwarf Cleric) → Dwarven Resilience fires
    because the spell deals poison damage. roll_request
    base_expression = 2d20kh1 + feature_used(source=dwarven-resilience)
    broadcast for Tavik.
    """
    thal = thalindra_rested
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_tok(thal), _tok(tavik)])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": POISON_SPRAY_THAL_INDEX,
            "slot_level": 0,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_race_{tavik['id']}",
            "target_character_id": tavik["id"],
            "target_name": tavik["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_ability"] == "CON"
    assert data["auto_save_target_kind"] == "pc"
    assert data["auto_save_prompted"] is True

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None, "expected a roll_request broadcast for Tavik's Con save"
    assert rr["data"]["base_expression"] == "2d20kh1", (
        f"Dwarven Resilience should set base_expression to 2d20kh1; "
        f"got {rr['data']['base_expression']!r}"
    )
    msgs = _race_save_broadcasts(gm_ws, tavik["id"], "dwarven-resilience")
    assert msgs, (
        f"expected feature_used(source=dwarven-resilience) for Tavik; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_dwarven_resilience_skips_non_poison_save(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Control: Fireball (Dex save, fire damage) at Tavik → Dwarven
    Resilience doesn't fire (the rule gates on poison only).
    Confirmed by base_expression staying 1d20 and no
    dwarven-resilience broadcast.
    """
    thal = thalindra_rested
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_tok(thal), _tok(tavik)])
    gm_ws.mark()
    # Fireball is index 7 in Thalindra's spell list (see Danger
    # Sense harness for the same assertion).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": 7,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_race_{tavik['id']}",
            "target_character_id": tavik["id"],
            "target_name": tavik["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"Fireball (fire damage) should NOT trigger Dwarven Resilience; "
        f"got base_expression={rr['data']['base_expression']!r}"
    )
    msgs = _race_save_broadcasts(gm_ws, tavik["id"], "dwarven-resilience")
    assert not msgs, (
        f"Dwarven Resilience broadcast should NOT fire on Fireball: {msgs}"
    )


async def test_dwarven_resilience_skips_non_dwarf_race(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """Control: Poison Spray at Thalindra herself (Elf) → Dwarven
    Resilience doesn't fire because Thalindra isn't a Dwarf.
    base_expression stays 1d20; no dwarven-resilience broadcast.
    (Fey Ancestry also doesn't fire because Poison Spray installs
    no condition — the spell-condition map is empty for poison-spray.)
    """
    thal = thalindra_rested
    await _seed_battle(gm_client, [_tok(thal)])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": POISON_SPRAY_THAL_INDEX,
            "slot_level": 0,
            "class_slug": "wizard",
            "target_combatant_id": f"tok_race_{thal['id']}",
            "target_character_id": thal["id"],
            "target_name": thal["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    rr = _roll_request_broadcast(gm_ws)
    assert rr is not None
    assert rr["data"]["base_expression"] == "1d20", (
        f"Elf has no Dwarven Resilience; "
        f"got base_expression={rr['data']['base_expression']!r}"
    )
    msgs = _race_save_broadcasts(gm_ws, thal["id"], "dwarven-resilience")
    assert not msgs, (
        f"Dwarven Resilience broadcast should NOT fire for Elf: {msgs}"
    )
