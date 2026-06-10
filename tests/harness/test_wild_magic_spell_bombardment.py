"""v2.99.231 — Wild Magic Sorcerer: Spell Bombardment (Phase 5).

Phase E.6 Phase 5 (FINAL) of the v2.99.193 phased completion
plan. RAW PHB p.103: "Beginning at 18th level, the harmful
energy of your spells intensifies. When you roll damage for a
spell and roll the highest number possible on any of the dice,
choose one of those dice, roll it again and add that roll to
the damage. You can use the feature only once per turn."

v1 ships:
  - /use_spell_bombardment: validates Wild Magic Lv 18+ + once-
    per-turn flag (combatant economy `spell_bombardment_used`,
    mirror of Colossus Slayer's flag); rolls 1d<die_size>;
    marks flag; broadcasts.

Zara Emberfire (Sorcerer Draconic Bloodline Lv 5 default).
Tests PATCH her subclass to "Wild Magic" + level to 18 and seed
her in a battle so the economy flag has a home.

Tests:
  - Happy path d8 → roll in 1..8, broadcast fired.
  - Once-per-turn flag: second invocation same turn → 409.
  - Bad die_size (5) → 400.
  - Wrong subclass (Draconic) → 409.
  - Level gate (Lv 17) → 409.
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


def _sb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "spell-bombardment"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_wild_magic_lv18(gm_client, roster):
    """PATCH Zara to Wild Magic + Lv 18 + seed in a fresh battle
    so the per-turn flag has somewhere to live."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Wild Magic", "level": 18},
        class_slug="sorcerer",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_sb_{zara['id']}",
             "char_id": zara["id"], "name": zara["name"],
             "initiative": 12, "hp_current": 90, "hp_max": 90,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield zara
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline", "level": 5},
            class_slug="sorcerer",
        )


_SB_BUFF = {
    "key": "spell-bombardment-active",
    "name": "💥 Spell Bombardment",
    "icon": "💥",
    "duration_rounds": 100000,
    "duration_max": 100000,
    "permanent": True,
    "concentration": False,
    "effects": {
        "spell_bombardment_active": True,
        "spell_bombardment_die_sizes": [4, 6, 8, 10, 12],
        "spell_bombardment_uses_per_turn": 1,
    },
}


async def _seed_zara_with_sb_buff(gm_client, zara, *, used=False):
    """v2.158.44 — re-seed the battle with Zara carrying the
    `spell-bombardment-active` buff so `/cast_spell`'s advisory read
    (`_pc_spell_bombardment_params` + `_is_spell_bombardment_used`)
    has both the buff and a known once-per-turn flag state. The buff
    shape mirrors the install contract pinned by
    `test_sb_buff_payload_carries_parameter_flags`."""
    econ = {"action": False, "bonus": False,
            "reaction": False, "movement": 0}
    if used:
        econ["spell_bombardment_used"] = True
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_sb_{zara['id']}",
             "char_id": zara["id"], "name": zara["name"],
             "initiative": 12, "hp_current": 90, "hp_max": 90,
             "buffs": [dict(_SB_BUFF)],
             "economy": econ},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _sheet_spells(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return list((r.json().get("sheet") or {}).get("spells") or [])


async def _spell_index_by_slug(gm_client, char_id, slug):
    for i, s in enumerate(await _sheet_spells(gm_client, char_id)):
        if (s.get("_slug") or "").lower() == slug:
            return i
    return None


async def test_sb_cast_damage_spell_surfaces_advisory(
    gm_client, zara_wild_magic_lv18,
):
    """v2.158.44 — Phase 2 read site for the v2.158.15 Spell Bombardment
    buff. A Lv 18 Wild Magic Zara carrying `spell-bombardment-active`
    (once-per-turn flag unused) who casts a damage cantrip (Fire Bolt,
    injected) sees `/cast_spell` surface `spell_bombardment_available ==
    True` + `spell_bombardment_uses_remaining == 1` + the eligible die
    sizes."""
    zara = zara_wild_magic_lv18
    await _seed_zara_with_sb_buff(gm_client, zara, used=False)
    original = await _sheet_spells(gm_client, zara["id"])
    injected = original + [{
        "name": "Fire Bolt", "level": 0, "prepared": True,
        "_slug": "fire-bolt", "casting_time": "1 action",
        "range": "120 feet", "school": "Evocation",
        "damage": "1d10", "damage_type": "fire",
    }]
    await _patch_sheet(gm_client, zara["id"], {"spells": injected})
    try:
        fb_index = await _spell_index_by_slug(
            gm_client, zara["id"], "fire-bolt")
        assert fb_index is not None, "Fire Bolt not injected"
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": zara["id"],
                "spell_index": fb_index,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("spell_bombardment_available") is True, (
            f"buff + damage spell + unused flag → available True; got {data}"
        )
        assert data.get("spell_bombardment_uses_remaining") == 1
        die_sizes = data.get("spell_bombardment_die_sizes") or []
        for ds in (4, 6, 8, 10, 12):
            assert ds in die_sizes, f"missing die {ds}; got {die_sizes}"
    finally:
        await _patch_sheet(gm_client, zara["id"], {"spells": original})


async def test_sb_advisory_not_surfaced_on_non_damage_spell(
    gm_client, zara_wild_magic_lv18,
):
    """Control: with the buff + unused flag, casting a non-damage cantrip
    (Light, injected — no `damage` dice) reports
    `spell_bombardment_available == False` + `uses_remaining == 0` +
    empty die sizes. Pins the damage-spell gate (the buff alone isn't
    enough)."""
    zara = zara_wild_magic_lv18
    await _seed_zara_with_sb_buff(gm_client, zara, used=False)
    original = await _sheet_spells(gm_client, zara["id"])
    injected = original + [{
        "name": "Light", "level": 0, "prepared": True,
        "_slug": "light", "casting_time": "1 action",
        "range": "Touch", "school": "Evocation",
    }]
    await _patch_sheet(gm_client, zara["id"], {"spells": injected})
    try:
        li_index = await _spell_index_by_slug(
            gm_client, zara["id"], "light")
        assert li_index is not None, "Light not injected"
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": zara["id"],
                "spell_index": li_index,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("spell_bombardment_available") is False, (
            f"non-damage spell → available False; got {data}"
        )
        assert data.get("spell_bombardment_uses_remaining") == 0
        assert (data.get("spell_bombardment_die_sizes") or []) == []
    finally:
        await _patch_sheet(gm_client, zara["id"], {"spells": original})


async def test_use_spell_bombardment_happy(
    gm_client, gm_ws, zara_wild_magic_lv18,
):
    """Lv 18 Wild Magic Zara → 1d8 reroll in 1..8 + broadcast +
    buff installed."""
    zara = zara_wild_magic_lv18
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 8},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["die_size"] == 8
    assert 1 <= data["extra_damage"] <= 8
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _sb_broadcasts(gm_ws, zara["id"])
    assert feats


async def test_sb_buff_payload_carries_parameter_flags(
    gm_client, gm_ws, zara_wild_magic_lv18,
):
    """v2.158.15 — state contract (Phase 9): the installed
    `spell-bombardment-active` buff carries the three
    `spell_bombardment_*` effect keys with the right values
    (active=True, die_sizes=[4,6,8,10,12], uses_per_turn=1).
    Phase 2 (deferred) will have `/cast_spell`'s damage-roll
    path read these off the caster's `_buffs_active` to auto-
    detect max-rolled dice and surface the reroll option; this
    test pins the flag shape so that future read site has a
    stable contract."""
    zara = zara_wild_magic_lv18
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 6},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    zara_buffs = bu["data"]["buffs"]
    sb_buff = next(
        (b for b in zara_buffs if b.get("key") == "spell-bombardment-active"),
        None,
    )
    assert sb_buff is not None, (
        f"spell-bombardment-active buff missing; got keys="
        f"{[b.get('key') for b in zara_buffs]}"
    )
    effects = sb_buff.get("effects") or {}
    assert effects.get("spell_bombardment_active") is True
    die_sizes = effects.get("spell_bombardment_die_sizes") or []
    for ds in (4, 6, 8, 10, 12):
        assert ds in die_sizes, (
            f"missing die_size {ds}; got {die_sizes}"
        )
    assert effects.get("spell_bombardment_uses_per_turn") == 1
    # Permanent passive — no concentration, very long duration.
    assert sb_buff.get("concentration") in (False, None)
    assert int(sb_buff.get("duration_rounds") or 0) >= 1000


async def test_use_spell_bombardment_once_per_turn(
    gm_client, zara_wild_magic_lv18,
):
    """First call succeeds; second call same turn → 409."""
    zara = zara_wild_magic_lv18
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 10},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 10},
    )
    assert r2.status_code == 409, r2.text
    data = r2.json()
    assert data.get("error") == "once_per_turn"


async def test_use_spell_bombardment_bad_die_size(
    gm_client, zara_wild_magic_lv18,
):
    """die_size=5 → 400."""
    zara = zara_wild_magic_lv18
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 5},
    )
    assert r.status_code == 400, r.text


async def test_use_spell_bombardment_wrong_subclass(
    gm_client, roster,
):
    """Default Draconic Bloodline → 409."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
        json={"character_id": zara["id"], "die_size": 8},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_spell_bombardment_level_gate(
    gm_client, roster,
):
    """Wild Magic at Lv 17 (not 18+) → 409."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Wild Magic", "level": 17},
        class_slug="sorcerer",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_spell_bombardment",
            json={"character_id": zara["id"], "die_size": 8},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline", "level": 5},
            class_slug="sorcerer",
        )
