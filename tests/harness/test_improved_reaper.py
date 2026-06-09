"""v2.99.297 → v2.158.9 — Death Domain Cleric: Improved Reaper (Lv 17).

v2.99.297 shipped announce-only. v2.158.9 (Phase 8 eighth feature
commit of the [full-feature-automation](../../docs/plans/full-feature-automation.md)
plan; CLOSES the Lv-17 cleric subclass capstone batch 6/6) wires
the endpoint to install a permanent `improved-reaper-active` buff
carrying the necromancy dual-target parameters:
  * `effects.improved_reaper_active: True`
  * `effects.improved_reaper_min_spell_level: 1`
  * `effects.improved_reaper_max_spell_level: 5`
  * `effects.improved_reaper_school: "necromancy"`
  * `effects.improved_reaper_max_targets: 2`
  * `effects.improved_reaper_max_target_separation_ft: 5`

Phase 1 of the standard install-then-deferred-read split (same
shape as v2.158.3 Improved Duplicity). Phase 2 (deferred):
`/cast_spell` reads the buff and accepts a second
`target_combatant_id` when the spell qualifies (necromancy school,
levels 1-5, default single-target shape).

RAW DMG p.97: 1st-5th level necromancy spells that target one
creature can target two creatures within range + within 5 ft of
each other.

Tests:
  - Lv 17 happy → max_targets 2, school necromancy, spell
    levels 1-5, buff_installed True.
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
  - Installed buff carries the six `improved_reaper_*` flags on
    `effects` with the right values.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _ir_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "improved-reaper"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _pc(cid, c, *, hp_max=80):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_tavik_in_battle(gm_client, tavik):
    """v2.158.9 — `_install_buff` requires an active battle. Seed a
    minimal one with Tavik so the endpoint can lay down the buff."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_ir_tavik_{tavik['id']}", tavik)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


@pytest_asyncio.fixture
async def tavik_death_lv17(gm_client, roster):
    """PATCH Tavik to Death Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Death Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_ir_happy_lv17(
    gm_client, gm_ws, tavik_death_lv17,
):
    """Lv 17 Death → necromancy Lv 1-5 → 2 targets, 5 ft apart,
    buff_installed True."""
    tavik = tavik_death_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_reaper",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_targets"] == 2
    assert data["max_target_separation_ft"] == 5
    assert data["school"] == "necromancy"
    assert data["min_spell_level"] == 1
    assert data["max_spell_level"] == 5
    assert data["cleric_level"] == 17
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _ir_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_ir_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_reaper",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ir_level_gate(
    gm_client, roster,
):
    """Death Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Death Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_improved_reaper",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_ir_buff_payload_carries_necromancy_dual_target_flags(
    gm_client, gm_ws, tavik_death_lv17,
):
    """v2.158.9 — state contract (Phase 9): the installed
    `improved-reaper-active` buff carries the six necromancy
    dual-target parameters on `effects`:
      * `improved_reaper_active: True`
      * `improved_reaper_min_spell_level: 1`
      * `improved_reaper_max_spell_level: 5`
      * `improved_reaper_school: "necromancy"`
      * `improved_reaper_max_targets: 2`
      * `improved_reaper_max_target_separation_ft: 5`
    Phase 2 (deferred) will have `/cast_spell` read these off
    the caster's `_buffs_active` and route a second target for
    qualifying single-target Lv-1-5 necromancy spells; this
    test pins the flag shape so that future read site has a
    stable contract."""
    tavik = tavik_death_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_reaper",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    tavik_buffs = bu["data"]["buffs"]
    ir_buff = next(
        (b for b in tavik_buffs if b.get("key") == "improved-reaper-active"),
        None,
    )
    assert ir_buff is not None, (
        f"improved-reaper-active buff missing; got keys="
        f"{[b.get('key') for b in tavik_buffs]}"
    )
    effects = ir_buff.get("effects") or {}
    assert effects.get("improved_reaper_active") is True
    assert effects.get("improved_reaper_min_spell_level") == 1
    assert effects.get("improved_reaper_max_spell_level") == 5
    assert effects.get("improved_reaper_school") == "necromancy"
    assert effects.get("improved_reaper_max_targets") == 2
    assert effects.get("improved_reaper_max_target_separation_ft") == 5
    # Permanent passive — no concentration, very long duration.
    assert ir_buff.get("concentration") in (False, None)
    assert int(ir_buff.get("duration_rounds") or 0) >= 1000
