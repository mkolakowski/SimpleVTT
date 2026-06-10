"""v2.99.225 — Evocation Wizard features: Sculpt Spells + Empowered Evocation.

Phase E.7 of the v2.99.193 phased completion plan. RAW PHB
p.117:
  - Sculpt Spells (Lv 2): on evocation cast, protect 1 + spell
    level chosen creatures from save-half damage.
  - Empowered Evocation (Lv 10): add INT mod to one damage roll
    of a wizard evocation spell.

v1 ships:
  - /use_sculpt_spells: announce, returns protected_count =
    1 + spell_level.
  - /use_empowered_evocation: announce, returns INT mod.

Thalindra Moonwhisper (Wizard School of Evocation Lv 7) is the
demo fixture. The Empowered Evocation test PATCHes her Lv 7 → 10.

Tests:
  - Sculpt Spells Lv 2 happy path (Thalindra at Lv 7 ≥ 2).
  - Sculpt Spells bad spell_level (0) → 400.
  - Sculpt Spells wrong-subclass gate (Magnus / Conjuration would
    work but he isn't a wizard — use Krieger, wrong class).
  - Empowered Evocation at Lv 10 happy path.
  - Empowered Evocation level gate (Lv 7).
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


def _sculpt_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "sculpt-spells"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _empowered_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "empowered-evocation"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def test_use_sculpt_spells_lv3_fireball(
    gm_client, gm_ws, roster,
):
    """Thalindra Lv 7, level-3 evocation → protected = 4 + broadcast."""
    thal = roster["Thalindra Moonwhisper"]
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_sculpt_spells",
        json={
            "character_id": thal["id"],
            "spell_level": 3,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["protected_count"] == 4
    assert data["spell_level"] == 3
    await asyncio.sleep(0.3)
    feats = _sculpt_broadcasts(gm_ws, thal["id"])
    assert feats
    assert feats[-1]["data"]["protected_count"] == 4


async def test_use_sculpt_spells_bad_level(
    gm_client, roster,
):
    """spell_level 0 → 400."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_sculpt_spells",
        json={
            "character_id": thal["id"],
            "spell_level": 0,
        },
    )
    assert r.status_code == 400, r.text


async def test_use_sculpt_spells_wrong_class(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409 wrong_subclass_or_level."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_sculpt_spells",
        json={
            "character_id": krieger["id"],
            "spell_level": 3,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


def _pc(cid, c, *, hp_max=40):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_thal_in_battle(gm_client, thal):
    """v2.158.19 — `_install_buff` requires an active battle."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_ee_thal_{thal['id']}", thal)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def test_use_empowered_evocation_at_lv10(
    gm_client, gm_ws, roster,
):
    """Thalindra PATCH'd to Lv 10 → +INT mod broadcast +
    buff_installed True."""
    thal = roster["Thalindra Moonwhisper"]
    pre_level = 7
    await _patch_sheet(
        gm_client, thal["id"], {"level": 10},
        class_slug="wizard",
    )
    try:
        await _seed_thal_in_battle(gm_client, thal)
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_empowered_evocation",
            json={"character_id": thal["id"]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["int_mod"] == 3  # INT 16 → +3
        assert data["buff_installed"] is True
        await asyncio.sleep(0.3)
        feats = _empowered_broadcasts(gm_ws, thal["id"])
        assert feats
        assert feats[-1]["data"]["int_mod"] == 3
    finally:
        await _patch_sheet(
            gm_client, thal["id"], {"level": pre_level},
            class_slug="wizard",
        )


async def _set_auto_apply(gm_client, on: bool):
    form = {
        "name": "Demo Campaign", "description": "demo",
        "game_system": "dnd5e", "gm_tab_color": "", "font_override": "",
        "default_encounter_id": "", "hp_threshold_1": "",
        "hp_threshold_2": "", "hp_threshold_3": "", "hp_threshold_4": "",
        "auto_play_playlist_id": "", "auto_play_mode": "order",
        "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form,
        follow_redirects=False,
    )


@pytest_asyncio.fixture
async def auto_apply_on(gm_client):
    await _set_auto_apply(gm_client, True)
    yield
    await _set_auto_apply(gm_client, False)


async def _fireball_index(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    spells = (r.json().get("sheet") or {}).get("spells") or []
    for i, s in enumerate(spells):
        if (s.get("_slug") or "").lower() == "fireball":
            return i
    raise AssertionError("Thalindra has no Fireball in her spell list")


async def _spell_index_by_slug(gm_client, char_id, slug):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    spells = (r.json().get("sheet") or {}).get("spells") or []
    for i, s in enumerate(spells):
        if (s.get("_slug") or "").lower() == slug:
            return i
    raise AssertionError(f"Thalindra has no {slug} in her spell list")


async def _seed_thal_vs_bandit(gm_client, thal):
    """Seed Thalindra + a 1-HP bandit NPC for a near-guaranteed
    Fireball save-path damage application. Returns the bandit id."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    bandit_id = f"tok_ee_bandit_{thal['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_ee_thal_{thal['id']}", thal),
            {"id": bandit_id, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 5,
             "hp_current": 40, "hp_max": 40, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    return bandit_id


async def test_empowered_evocation_adds_int_to_fireball_damage(
    gm_client, gm_ws, roster, auto_apply_on,
):
    """v2.158.32 — Phase 2 read site: Thalindra (Evocation Wizard,
    PATCH'd to Lv 10) installs the empowered-evocation-active buff,
    then casts Fireball (evocation, DEX save) at an NPC bandit. The
    /cast_spell save path reads the buff via the spell's school and
    fires a feature_used(source=empowered-evocation-bonus) with the
    +INT (3) bonus + applies damage."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"], {"level": 10}, class_slug="wizard",
    )
    try:
        bandit_id = await _seed_thal_vs_bandit(gm_client, thal)
        fb_index = await _fireball_index(gm_client, thal["id"])
        # Install the Empowered Evocation buff.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_empowered_evocation",
            json={"character_id": thal["id"]},
        )
        assert r.status_code == 200, r.text
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": fb_index,
                "target_combatant_id": bandit_id,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        await asyncio.sleep(0.3)
        bonus = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source")
            == "empowered-evocation-bonus"
            and (m.get("data") or {}).get("character_id") == thal["id"]
        ]
        assert bonus, (
            "expected empowered-evocation-bonus feature_used after a "
            "Fireball cast with the buff active"
        )
        assert "+3" in bonus[-1]["data"]["feature_name"], (
            f"expected +3 (INT mod) in the bonus label; got "
            f"{bonus[-1]['data']['feature_name']!r}"
        )
    finally:
        await _patch_sheet(
            gm_client, thal["id"], {"level": 7}, class_slug="wizard",
        )


async def test_empowered_evocation_adds_int_on_attack_roll_path(
    gm_client, gm_ws, roster, auto_apply_on,
):
    """v2.158.33 — attack-roll read site: Thalindra (Evocation Wizard
    PATCH'd to Lv 10) with the buff installed casts Fire Bolt (evocation
    cantrip, spell attack roll) at an NPC bandit. When a beam hits, the
    /cast_spell attack-roll path adds +INT (3) to the aggregate damage
    and fires feature_used(source=empowered-evocation-bonus). Fire Bolt
    is a cantrip → no slot, so loop until a hit lands."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"], {"level": 10}, class_slug="wizard",
    )
    try:
        bandit_id = await _seed_thal_vs_bandit(gm_client, thal)
        fb_index = await _spell_index_by_slug(
            gm_client, thal["id"], "fire-bolt",
        )
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_empowered_evocation",
            json={"character_id": thal["id"]},
        )
        assert r.status_code == 200, r.text
        gm_ws.mark()
        fired = False
        for _ in range(20):
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": thal["id"],
                    "spell_index": fb_index,
                    "target_combatant_id": bandit_id,
                    "override": True,
                    "override_range": True,
                },
            )
            assert r.status_code == 200, r.text
            if r.json().get("auto_attack_hit"):
                fired = True
                break
        assert fired, "Fire Bolt never hit the bandit in 20 casts"
        await asyncio.sleep(0.3)
        bonus = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source")
            == "empowered-evocation-bonus"
            and (m.get("data") or {}).get("character_id") == thal["id"]
        ]
        assert bonus, (
            "expected empowered-evocation-bonus after a Fire Bolt hit "
            "with the buff active"
        )
        assert "+3" in bonus[-1]["data"]["feature_name"]
    finally:
        await _patch_sheet(
            gm_client, thal["id"], {"level": 7}, class_slug="wizard",
        )


async def test_empowered_evocation_bonus_absent_without_buff(
    gm_client, gm_ws, roster, auto_apply_on,
):
    """Control: Thalindra at Lv 10 but WITHOUT installing the buff —
    casting Fireball does NOT emit an empowered-evocation-bonus. Pins
    the buff-gate (school alone isn't enough)."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"], {"level": 10}, class_slug="wizard",
    )
    try:
        bandit_id = await _seed_thal_vs_bandit(gm_client, thal)
        fb_index = await _fireball_index(gm_client, thal["id"])
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": fb_index,
                "target_combatant_id": bandit_id,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        await asyncio.sleep(0.3)
        bonus = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source")
            == "empowered-evocation-bonus"
        ]
        assert not bonus, (
            f"empowered-evocation-bonus should NOT fire without the "
            f"buff installed; got {bonus}"
        )
    finally:
        await _patch_sheet(
            gm_client, thal["id"], {"level": 7}, class_slug="wizard",
        )


async def test_use_empowered_evocation_level_gate(
    gm_client, roster,
):
    """Control: Thalindra at Lv 7 → 409 wrong_subclass_or_level."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_empowered_evocation",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_ee_buff_payload_carries_int_mod_and_school_flags(
    gm_client, gm_ws, roster,
):
    """v2.158.19 — state contract (Phase 9): the installed
    `empowered-evocation-active` buff carries three
    `empowered_evocation_*` effect keys with the right values
    (active=True, int_mod=3 for Thalindra's INT 16, school="evocation").
    Phase 2 (deferred) will have `/cast_spell` read these off
    the caster's `_buffs_active` and offer +INT to one damage
    roll per evocation cast; this test pins the flag shape so
    that future read site has a stable contract."""
    thal = roster["Thalindra Moonwhisper"]
    pre_level = 7
    await _patch_sheet(
        gm_client, thal["id"], {"level": 10},
        class_slug="wizard",
    )
    try:
        await _seed_thal_in_battle(gm_client, thal)
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_empowered_evocation",
            json={"character_id": thal["id"]},
        )
        assert r.status_code == 200, r.text
        bu = await gm_ws.wait_for("buff_update")
        thal_buffs = bu["data"]["buffs"]
        ee_buff = next(
            (b for b in thal_buffs
             if b.get("key") == "empowered-evocation-active"),
            None,
        )
        assert ee_buff is not None, (
            f"empowered-evocation-active buff missing; got keys="
            f"{[b.get('key') for b in thal_buffs]}"
        )
        effects = ee_buff.get("effects") or {}
        assert effects.get("empowered_evocation_active") is True
        assert effects.get("empowered_evocation_int_mod") == 3
        assert effects.get("empowered_evocation_school") == "evocation"
        # Permanent passive — no concentration, very long duration.
        assert ee_buff.get("concentration") in (False, None)
        assert int(ee_buff.get("duration_rounds") or 0) >= 1000
    finally:
        await _patch_sheet(
            gm_client, thal["id"], {"level": pre_level},
            class_slug="wizard",
        )
