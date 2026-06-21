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
        # Place the caster outside the 10-ft barrier (25 ft) so the gate
        # fires deterministically — demo PCs are seeded with tokens, so
        # we can't rely on an off-grid `None` distance here.
        await _place(gm_client, thal["id"], 350.0, 350.0)
        await _place(gm_client, zara["id"], 700.0, 350.0)
        r = await _cast_mm(gm_client, zara, thal, thal_tok, mm_idx)
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "globe_blocks_spell", r.json()
    finally:
        await _drop_globe(gm_client, thal)
        await _del_token(gm_client, thal["id"])
        await _del_token(gm_client, zara["id"])


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
        # Caster outside the barrier so the gate fires (see note above).
        await _place(gm_client, thal["id"], 350.0, 350.0)
        await _place(gm_client, zara["id"], 700.0, 350.0)
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
        await _del_token(gm_client, thal["id"])
        await _del_token(gm_client, zara["id"])


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


# --- v2.517.0 — Phase 2: inside/outside-the-barrier enforcement ---------
# The off-grid tests above prove the "assume outside" fallback (no tokens
# placed → blocked). These two place tokens so the distance check decides.
# Grid: 70 px / cell, 5 ft / cell; the globe radius is 10 ft (2 cells).


async def _place(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _del_token(gm_client, char_id):
    await gm_client.delete(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/token",
    )


async def _cast_mm(gm_client, zara, thal, thal_tok, mm_idx):
    return await gm_client.post(
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


async def test_globe_blocks_caster_outside_barrier(gm_client, roster):
    """Caster 25 ft from the globe holder (outside the 10-ft barrier) →
    409 globe_blocks_spell."""
    zara, thal, thal_tok, mm_idx = await _setup(gm_client, roster)
    try:
        await _raise_globe(gm_client, thal)
        await _place(gm_client, thal["id"], 350.0, 350.0)
        await _place(gm_client, zara["id"], 700.0, 350.0)  # 5 cells = 25 ft
        r = await _cast_mm(gm_client, zara, thal, thal_tok, mm_idx)
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "globe_blocks_spell", r.json()
    finally:
        await _drop_globe(gm_client, thal)
        await _del_token(gm_client, thal["id"])
        await _del_token(gm_client, zara["id"])


async def test_globe_does_not_block_caster_inside_barrier(gm_client, roster):
    """Caster 5 ft from the globe holder (inside the 10-ft barrier) → the
    globe gate does NOT fire (a creature inside casts freely)."""
    zara, thal, thal_tok, mm_idx = await _setup(gm_client, roster)
    try:
        await _raise_globe(gm_client, thal)
        await _place(gm_client, thal["id"], 350.0, 350.0)
        await _place(gm_client, zara["id"], 420.0, 350.0)  # 1 cell = 5 ft
        r = await _cast_mm(gm_client, zara, thal, thal_tok, mm_idx)
        if r.status_code == 409:
            assert r.json().get("error") != "globe_blocks_spell", r.json()
    finally:
        await _drop_globe(gm_client, thal)
        await _del_token(gm_client, thal["id"])
        await _del_token(gm_client, zara["id"])


async def test_globe_off_grid_assumes_outside_and_blocks(gm_client, roster):
    """Off-grid (no tokens on the map) → `None` distance → the gate
    assumes the caster is outside and blocks (the v2.513.0 fallback)."""
    zara, thal, thal_tok, mm_idx = await _setup(gm_client, roster)
    try:
        await _raise_globe(gm_client, thal)
        # Force off-grid by removing any seeded tokens for both.
        await _del_token(gm_client, thal["id"])
        await _del_token(gm_client, zara["id"])
        r = await _cast_mm(gm_client, zara, thal, thal_tok, mm_idx)
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "globe_blocks_spell", r.json()
        assert r.json().get("caster_distance_ft") is None, r.json()
    finally:
        await _drop_globe(gm_client, thal)
