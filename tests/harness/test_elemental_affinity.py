"""v2.99.43 — Elemental Affinity (Draconic Bloodline Sorcerer Lv 6).

RAW (PHB p.103): "At 6th level, when you cast a spell that deals
damage of the type associated with your draconic ancestry, you can
add your Charisma modifier to one damage roll of that spell. At the
same time, you can spend 1 sorcery point to gain resistance to that
damage type for 1 hour."

Two parts:
- Passive damage bonus auto-fires at /cast_spell single-target damage
  site when spell's damage_type matches the ancestor's type (Zara →
  Red → fire). Appends "+CHA" to the damage_expr before rolling.
  Companion broadcast: feature_used(source=elemental-affinity-bonus).
- Optional /use_elemental_affinity endpoint: 1 SP arms an
  `elemental-affinity-resistance` buff with `effects.resistance_to:
  [drac_type]`. _resistance_halve reads the field and halves damage
  of that type taken by the caster for 1 hour (600 rounds).

Tests use the v2.99.39 capstone-test pattern (class-scoped level
PATCH) to temporarily bump Zara to Lv 6.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Zara's spell list — Fireball at index 11.
FIREBALL_ZARA_INDEX = 11


@pytest_asyncio.fixture
async def zara_at_lv_6(gm_client, roster):
    """Bump Zara to Lv 6 for the test, restore at end."""
    zara = roster["Zara Emberfire"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"class_slug": "sorcerer", "level": 6},
    )
    yield zara
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
        json={"class_slug": "sorcerer", "level": 5},
    )


async def _seed_zara_vs_bandit(gm_client, zara):
    """Two-combatant battle: Zara + a bandit NPC."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": f"tok_ea_{zara['id']}", "char_id": zara["id"],
                 "name": zara["name"], "initiative": 10,
                 "hp_current": 37, "hp_max": 37, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": "tok_ea_bandit", "char_id": None,
                 "token_template_id": bandit_tmpl["id"],
                 "name": bandit_tmpl["name"], "initiative": 7,
                 "hp_current": 200, "hp_max": 200, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return bandit_tmpl


async def _set_auto_apply(gm_client, on: bool) -> None:
    form = {
        "name": "Demo Campaign", "description": "demo",
        "game_system": "dnd5e", "gm_tab_color": "",
        "font_override": "", "default_encounter_id": "",
        "hp_threshold_1": "", "hp_threshold_2": "",
        "hp_threshold_3": "", "hp_threshold_4": "",
        "auto_play_playlist_id": "", "auto_play_mode": "order",
        "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form,
        follow_redirects=False,
    )


# ---------- (1) Passive damage bonus ----------

async def test_elemental_affinity_bonus_broadcast_on_fire_spell(
    gm_client, gm_ws, zara_at_lv_6,
):
    """Lv 6 Zara casts Fireball (fire) at a bandit. Asserts the
    feature_used(source=elemental-affinity-bonus) broadcast fires
    (proves the gate matched + bonus applied to the damage roll).
    """
    zara = zara_at_lv_6
    bandit_tmpl = await _seed_zara_vs_bandit(gm_client, zara)
    await _set_auto_apply(gm_client, on=True)

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": FIREBALL_ZARA_INDEX,
            "slot_level": 3,
            "class_slug": "sorcerer",
            "target_combatant_id": "tok_ea_bandit",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["auto_save_damage_type"] == "fire"

    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    bonus = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "elemental-affinity-bonus"
        and (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    assert bonus, (
        f"expected feature_used(source=elemental-affinity-bonus); "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_elemental_affinity_bonus_skips_at_lv_5(
    gm_client, gm_ws, roster,
):
    """Lv 5 Zara casts Fireball → NO Elemental Affinity broadcast
    (level gate at 6).
    """
    zara = roster["Zara Emberfire"]
    bandit_tmpl = await _seed_zara_vs_bandit(gm_client, zara)
    await _set_auto_apply(gm_client, on=True)

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": FIREBALL_ZARA_INDEX,
            "slot_level": 3,
            "class_slug": "sorcerer",
            "target_combatant_id": "tok_ea_bandit",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    bonus = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "elemental-affinity-bonus"
    ]
    assert not bonus, (
        f"Lv 5 should NOT trigger Elemental Affinity bonus; got {bonus}"
    )


# ---------- (2) Resistance endpoint ----------

async def test_elemental_affinity_resistance_endpoint_arms_buff(
    gm_client, zara_at_lv_6,
):
    """1 SP → 200 + `elemental-affinity-resistance` buff installed
    on Zara with `effects.resistance_to: ["fire"]`. Endpoint returns
    `damage_type: "fire"` for the Red Dragon ancestor.
    """
    zara = zara_at_lv_6
    await _seed_zara_vs_bandit(gm_client, zara)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_elemental_affinity",
        json={"character_id": zara["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sp_cost"] == 1
    assert data["damage_type"] == "fire"
    assert data["sp_remaining"] == data["sp_max"] - 1

    zara_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/buffs"
    )).json().get("buffs", [])
    ea = next(
        (b for b in zara_buffs
         if (b or {}).get("key") == "elemental-affinity-resistance"),
        None,
    )
    assert ea is not None, (
        f"expected elemental-affinity-resistance buff; got {zara_buffs}"
    )
    resists = (ea.get("effects") or {}).get("resistance_to") or []
    assert "fire" in resists, (
        f"expected fire in resistance_to; got {resists}"
    )


async def test_elemental_affinity_level_too_low(gm_client, roster):
    """Lv 5 Zara → 409 level_too_low (required 6)."""
    zara = roster["Zara Emberfire"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_elemental_affinity",
        json={"character_id": zara["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "level_too_low"
    assert body["required"] == 6


async def test_elemental_affinity_wrong_class(gm_client, roster):
    """Tavik (Cleric) → 409 wrong_class."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_elemental_affinity",
        json={"character_id": tavik["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "wrong_class"


# v2.99.48 — AoE wire. RAW "one damage roll of that spell" means the
# +CHA bonus applies to ONE target's damage roll per cast, NOT every
# target in the AoE. The single-target NPC path (v2.99.43) handles
# target #0; the AoE NPC loop only fires the bonus if the
# single-target path didn't (e.g. when target #0 was a PC, or when
# there's no explicit single target).


async def _seed_zara_vs_two_bandits(gm_client, zara):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": f"tok_ea_{zara['id']}", "char_id": zara["id"],
                 "name": zara["name"], "initiative": 10,
                 "hp_current": 37, "hp_max": 37, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": "tok_ea_bandit1", "char_id": None,
                 "token_template_id": bandit_tmpl["id"],
                 "name": bandit_tmpl["name"], "initiative": 7,
                 "hp_current": 200, "hp_max": 200, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": "tok_ea_bandit2", "char_id": None,
                 "token_template_id": bandit_tmpl["id"],
                 "name": bandit_tmpl["name"], "initiative": 5,
                 "hp_current": 200, "hp_max": 200, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return bandit_tmpl


async def test_elemental_affinity_aoe_fires_exactly_once(
    gm_client, gm_ws, zara_at_lv_6,
):
    """Lv 6 Zara casts Fireball at TWO bandits via target_combatant_ids.
    RAW "one damage roll" — the +CHA bonus should fire EXACTLY ONCE
    (on target #0, the single-target NPC path), not twice.
    """
    zara = zara_at_lv_6
    bandit_tmpl = await _seed_zara_vs_two_bandits(gm_client, zara)
    await _set_auto_apply(gm_client, on=True)

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": FIREBALL_ZARA_INDEX,
            "slot_level": 3,
            "class_slug": "sorcerer",
            "target_combatant_id": "tok_ea_bandit1",
            "target_name": bandit_tmpl["name"],
            "target_combatant_ids": [
                "tok_ea_bandit1",
                "tok_ea_bandit2",
            ],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    bonus = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "elemental-affinity-bonus"
        and (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    assert len(bonus) == 1, (
        f"expected EXACTLY ONE Elemental Affinity bonus broadcast "
        f"per cast (RAW 'one damage roll'); got {len(bonus)}: "
        f"{[(m.get('data') or {}).get('source') for m in fu_msgs]}"
    )
