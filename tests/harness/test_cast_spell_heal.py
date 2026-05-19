"""Phase T.4 — /cast_spell auto-applies healing to the targeted ally.

v2.26.0: when a spell has a healing dice expression AND the caster
passes target_combatant_id (set by double-clicking an ally on the
map), the server rolls the heal + applies HP to the target via
``_apply_heal_to_combatant``. The legacy ``_heal_claims`` opt-in
flow stays for casts without a target.

Heals always auto-apply when target is set (no campaign toggle —
heals are low-risk; the chat-card ↶ Undo button reverts misclicks).

Tests:
  - Tavik casts Healing Word on Pip (PC target with reduced HP) →
    auto_heal_applied > 0, target_hp_after > target_hp_before
  - cast with no target → no auto-heal, heal_claim still registered
  - heal can revive a dying target (HP 0 → HP X, status alive)
  - Undo reverses the heal via /undo_attack_damage
  - Heal caps at max HP (no overheal)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def tavik_full(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


async def _set_pip_hp(gm_client, pip_id, hp_current):
    """Set Pip's HP directly so the heal has room to apply."""
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip_id}/sheet-fields",
        json={"hp": {"current": hp_current}},
    )


async def _seed_battle(gm_client, char_entries):
    combatants = []
    for e in char_entries:
        cid = e["id"]
        combatants.append({
            "id": f"tok_test_{cid}",
            "char_id": cid,
            "name": e.get("name") or f"PC {cid}",
            "initiative": 10,
            "hp_current": e.get("hp_current", 30),
            "hp_max": e.get("hp_max", 30),
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_heal_auto_applies_on_target(gm_client, tavik_full, roster):
    """Tavik casts Healing Word on Pip (HP reduced). Auto-heal applies
    HP to Pip's sheet. Response carries auto_heal_applied > 0."""
    tavik = tavik_full
    pip = roster["Pip Quickfingers"]
    # Reduce Pip's HP so the heal has room.
    await _set_pip_hp(gm_client, pip["id"], 10)
    await _seed_battle(gm_client, [
        {"id": tavik["id"], "name": tavik["name"]},
        {"id": pip["id"], "name": pip["name"]},
    ])
    HEALING_WORD_INDEX = 5  # See test_cast_spell.py for index notes.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_character_id": pip["id"],
            "target_combatant_id": f"tok_test_{pip['id']}",
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Auto-heal fields populated.
    assert data["auto_heal_applied"] > 0, "expected heal to apply when target set"
    assert data["auto_heal_target_name"] == pip["name"]
    assert data["auto_heal_hp_after"] is not None
    # Pip's HP went up.
    assert data["auto_heal_hp_after"] > 10


async def test_cast_without_target_no_auto_heal(gm_client, tavik_full):
    """Cast without target → no auto-heal (heal_claim path stays for opt-in)."""
    tavik = tavik_full
    HEALING_WORD_INDEX = 5
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_heal_applied"] == 0
    assert data["auto_heal_target_name"] == ""


async def test_heal_revives_dying_target(gm_client, tavik_full, roster):
    """Pip drops to 0 HP (dying). Tavik's Healing Word brings him back.
    auto_heal_revived flag set."""
    tavik = tavik_full
    pip = roster["Pip Quickfingers"]
    # First drop Pip to 0 HP via damage path so death-save state goes
    # to "dying" cleanly.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={
            "hp": {"current": 0},
            "hp_change_reason": "damage",
            "damage_amount": 30,
            "damage_type": "slashing",
        },
    )
    await _seed_battle(gm_client, [
        {"id": tavik["id"], "name": tavik["name"]},
        {"id": pip["id"], "name": pip["name"], "hp_current": 0},
    ])
    HEALING_WORD_INDEX = 5
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_character_id": pip["id"],
            "target_combatant_id": f"tok_test_{pip['id']}",
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_heal_applied"] > 0
    assert data["auto_heal_hp_after"] > 0  # No longer at 0.
    assert data["auto_heal_revived"] is True


async def test_undo_heal_reverses_hp(gm_client, tavik_full, roster):
    """Apply heal, undo via /undo_attack_damage → HP reverts."""
    tavik = tavik_full
    pip = roster["Pip Quickfingers"]
    await _set_pip_hp(gm_client, pip["id"], 5)
    await _seed_battle(gm_client, [
        {"id": tavik["id"], "name": tavik["name"]},
        {"id": pip["id"], "name": pip["name"], "hp_current": 5},
    ])
    HEALING_WORD_INDEX = 5
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_character_id": pip["id"],
            "target_combatant_id": f"tok_test_{pip['id']}",
            "target_name": pip["name"],
            "override": True,
        },
    )
    data = resp.json()
    cast_id = data["id"]
    applied = data["auto_heal_applied"]
    hp_after = data["auto_heal_hp_after"]
    assert applied > 0

    # Undo: server should detect is_heal entry and reverse by damaging.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert r.status_code == 200, r.text
    undo_data = r.json()
    assert undo_data["was_heal"] is True
    assert undo_data["reverted"] == applied
    assert undo_data["hp_after"] == hp_after - applied


async def test_heal_auto_applies_with_only_character_id(gm_client, tavik_full, roster):
    """v2.27.2: when the target PC isn't in the init tracker (no
    combatant entry yet) but target_character_id is set, auto-heal
    should still fire via the synthesized-combatant fallback. The PC
    heal path in ``_apply_heal_to_combatant`` only needs char_id —
    no init slot required. Repros the Cure Wounds bug where target
    was set client-side but the heal silently dropped into the legacy
    heal-claim flow because target_combatant_id wasn't resolved."""
    tavik = tavik_full
    pip = roster["Pip Quickfingers"]
    await _set_pip_hp(gm_client, pip["id"], 10)
    # Deliberately seed a battle with ONLY Tavik — no Pip combatant.
    # Mimics the situation where the GM cast Cure Wounds at a PC
    # whose token wasn't yet pulled into the init tracker.
    await _seed_battle(gm_client, [
        {"id": tavik["id"], "name": tavik["name"]},
    ])
    HEALING_WORD_INDEX = 5
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            # NO target_combatant_id — only character_id + name.
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_heal_applied"] > 0, "expected fallback auto-heal via target_character_id"
    assert data["auto_heal_hp_after"] > 10


async def test_heal_caps_at_max_hp(gm_client, tavik_full, roster):
    """When healing would overshoot max HP, the applied amount is
    clamped. auto_heal_applied reflects the actual increase, not the
    rolled dice."""
    tavik = tavik_full
    pip = roster["Pip Quickfingers"]
    # Set Pip to max - 1 so most of the heal is wasted.
    pip_max = pip.get("hp_max", 33) or 33
    await _set_pip_hp(gm_client, pip["id"], pip_max - 1)
    await _seed_battle(gm_client, [
        {"id": tavik["id"], "name": tavik["name"]},
        {"id": pip["id"], "name": pip["name"], "hp_current": pip_max - 1, "hp_max": pip_max},
    ])
    HEALING_WORD_INDEX = 5
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_character_id": pip["id"],
            "target_combatant_id": f"tok_test_{pip['id']}",
            "target_name": pip["name"],
            "override": True,
        },
    )
    data = resp.json()
    # Only 1 HP could be applied (max - 1 → max).
    assert data["auto_heal_applied"] == 1
    assert data["auto_heal_hp_after"] == pip_max
