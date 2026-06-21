"""Globe of Invulnerability — /cast_spell block. Phase 2 #44 follow-up
of ``docs/plans/cast-and-broadcast-tail.md``.

v2.513.0 — RAW PHB p.247: "Any spell of 5th level or lower cast from
outside the barrier can't affect creatures or objects within it, even
if the spell is cast using a higher level spell slot." New
`_target_globe_blocks_spell` hub-read folded into `/cast_spell` as a
pre-slot-consumption 409 `globe_blocks_spell` gate (single-target only;
self-casts skipped; GM `override` bypasses).

Setup: Thalindra (Wizard) raises Globe of Invulnerability on herself;
Zara (Sorcerer) casts Magic Missile (base level 1) at her.

Tests:
  - A level-≤5 spell at a globed target → 409 globe_blocks_spell.
  - Control: no globe → the same cast is not globe-blocked.
  - Upcast still blocked: Magic Missile at slot_level 5 → still 409
    (the comparison is the BASE level, not the slot).
  - GM override bypasses the gate.
"""
from .conftest import CAMPAIGN_ID


async def _spell_index(gm_client, char_id, name):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = (r.json() or {}).get("sheet") or {}
    for i, sp in enumerate(sheet.get("spells") or []):
        nm = sp.get("name") if isinstance(sp, dict) else sp
        if str(nm).strip().lower() == name.strip().lower():
            return i
    return -1


def _tok(char, tid, init=10, hp=60):
    return {
        "id": tid,
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _set_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _setup(gm_client, roster):
    """Returns (zara, thal, thal_tok, mm_idx) with Thalindra globed and
    Zara rested. Skips if the demo lacks the casters or Magic Missile."""
    import pytest
    zara = roster.get("Zara Emberfire")
    thal = roster.get("Thalindra Moonwhisper")
    if not (zara and thal):
        pytest.skip("demo roster missing Zara/Thalindra")
    mm_idx = await _spell_index(gm_client, zara["id"], "Magic Missile")
    if mm_idx < 0:
        pytest.skip("Zara must know Magic Missile")
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    thal_tok = f"tok_globe_thal_{thal['id']}"
    await _set_battle(gm_client, [
        _tok(zara, f"tok_globe_zara_{zara['id']}", init=20),
        _tok(thal, thal_tok, init=10),
    ])
    return zara, thal, thal_tok, mm_idx


async def _raise_globe(gm_client, thal):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_globe_of_invulnerability",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text


async def _drop_globe(gm_client, thal):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": thal["id"], "key": "globe-of-invulnerability"},
    )


async def test_globe_blocks_low_level_spell(gm_client, roster):
    """A level-≤5 spell cast at a globed target → 409 globe_blocks_spell
    (before slot consumption)."""
    zara, thal, thal_tok, mm_idx = await _setup(gm_client, roster)
    try:
        await _raise_globe(gm_client, thal)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": zara["id"],
                "spell_index": mm_idx,
                "class_slug": "sorcerer",
                "target_combatant_id": thal_tok,
                "target_character_id": thal["id"],
                "target_name": thal["name"],
                "override_range": True,
            },
        )
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "globe_blocks_spell", r.json()
    finally:
        await _drop_globe(gm_client, thal)


async def test_no_globe_does_not_block(gm_client, roster):
    """Control: with no globe up, the same cast is not globe-blocked."""
    zara, thal, thal_tok, mm_idx = await _setup(gm_client, roster)
    await _drop_globe(gm_client, thal)  # ensure no globe
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": mm_idx,
            "class_slug": "sorcerer",
            "target_combatant_id": thal_tok,
            "target_character_id": thal["id"],
            "target_name": thal["name"],
            "override_range": True,
        },
    )
    # Not the globe gate (200 success, or some other non-globe outcome).
    if r.status_code == 409:
        assert r.json().get("error") != "globe_blocks_spell", r.json()


async def test_globe_blocks_even_when_upcast(gm_client, roster):
    """RAW: a base level-≤5 spell upcast with a higher slot is still
    blocked — the comparison is the BASE level, not the slot."""
    zara, thal, thal_tok, mm_idx = await _setup(gm_client, roster)
    try:
        await _raise_globe(gm_client, thal)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": zara["id"],
                "spell_index": mm_idx,
                "slot_level": 5,  # upcast — base level is still 1
                "class_slug": "sorcerer",
                "target_combatant_id": thal_tok,
                "target_character_id": thal["id"],
                "target_name": thal["name"],
                "override_range": True,
            },
        )
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "globe_blocks_spell", r.json()
        assert r.json()["spell_level"] == 1, r.json()
    finally:
        await _drop_globe(gm_client, thal)


async def test_globe_override_bypasses_block(gm_client, roster):
    """GM override:true bypasses the globe gate."""
    zara, thal, thal_tok, mm_idx = await _setup(gm_client, roster)
    try:
        await _raise_globe(gm_client, thal)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": zara["id"],
                "spell_index": mm_idx,
                "class_slug": "sorcerer",
                "target_combatant_id": thal_tok,
                "target_character_id": thal["id"],
                "target_name": thal["name"],
                "override": True,
                "override_range": True,
            },
        )
        # The globe gate must not fire when override is set.
        if r.status_code == 409:
            assert r.json().get("error") != "globe_blocks_spell", r.json()
    finally:
        await _drop_globe(gm_client, thal)
