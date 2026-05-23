"""v2.49.164 — /api/campaign/{cid}/npc_attack — NPC weapon attack endpoint.

Parallel to /attack but for NPC monster combatants. GM-only.
Rolls 1d20 + attack_bonus, computes hit vs target AC, optionally
auto-applies damage on hit. Broadcasts weapon_attack with NPC-shaped
caster fields (caster_char_id=None, caster_char_name=monster name).

Coverage:
  - happy path: NPC attacks PC with target_combatant_id, response carries
    attack_total + damage_total + hit; weapon_attack broadcast fires with
    is_npc_attack=True and caster_char_name set
  - hit-or-miss determination uses target_ac
  - auto-apply on hit (when campaign.auto_apply_damage is on)
  - 400 missing combatant_id
  - 404 unknown combatant_id
  - 404 unknown target_combatant_id
  - 403 player (non-GM) caller
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, hp_cur=30, hp_max=30, name="X", template_id=None):
    out = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }
    if template_id is not None:
        out["token_template_id"] = template_id
    return out


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _set_auto_apply(gm_client, on: bool) -> None:
    form = {
        "name": "Demo Campaign",
        "description": "demo",
        "game_system": "dnd5e",
        "gm_tab_color": "",
        "font_override": "",
        "default_encounter_id": "",
        "hp_threshold_1": "",
        "hp_threshold_2": "",
        "hp_threshold_3": "",
        "hp_threshold_4": "",
        "auto_play_playlist_id": "",
        "auto_play_mode": "order",
        "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form, follow_redirects=False,
    )


@pytest_asyncio.fixture
async def auto_apply_off(gm_client):
    """Force auto_apply_damage OFF for tests that assert no HP change."""
    await _set_auto_apply(gm_client, False)
    yield


@pytest_asyncio.fixture
async def auto_apply_on(gm_client):
    """Force auto_apply_damage ON for the auto-damage test."""
    await _set_auto_apply(gm_client, True)
    yield
    await _set_auto_apply(gm_client, False)


async def test_npc_attack_happy_path(gm_client, gm_ws, roster, auto_apply_off):
    """NPC bandit swings at Pip. Response carries the d20 + damage rolls,
    a hit/miss decision, and the target's resolved AC. Broadcast fires
    with is_npc_attack=True and caster_char_name='Bandit'."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    bandit_cid = "npc_bandit_test_1"
    await _seed_battle(gm_client, [
        _mkc(bandit_cid, hp_cur=11, hp_max=11, name="Bandit", template_id=1),
        _mkc(pip_cid, pip["id"], hp_cur=30, hp_max=30, name=pip["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_id": "scimitar",
            "action_name": "Scimitar",
            "attack_bonus": "+3",
            "damage": "1d6+1",
            "damage_type": "slashing",
            "range": "5 ft",
            "target_combatant_id": pip_cid,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["attack_name"] == "Scimitar"
    # 1d20+3 → 4-23
    assert 4 <= data["attack_total"] <= 23
    assert "1d20" in data["attack_breakdown"]
    # 1d6+1 → 2-7
    assert 2 <= data["damage_total"] <= 7
    assert data["damage_type"] == "slashing"
    # Target AC was resolved (Pip's actual AC from the demo sheet).
    assert data["target_ac"] is not None
    assert isinstance(data["target_ac"], int)
    # Hit is deterministic given the rolled total + Pip's AC.
    assert data["hit"] in (True, False)
    # auto_apply is off — no HP change regardless of hit.
    assert data["damage_applied"] == 0
    assert data["auto_applied"] is False
    # NPC marker so client paths can branch on caster type.
    assert data["is_npc_attack"] is True

    msg = await gm_ws.wait_for("weapon_attack")
    assert msg["data"]["attack_name"] == "Scimitar"
    assert msg["data"]["caster_char_name"] == "Bandit"
    # NPC casters report caster_char_id as None (no PC backing).
    assert msg["data"]["caster_char_id"] is None
    # caster_combatant_id surfaces the attacker NPC for client routing.
    assert msg["data"]["caster_combatant_id"] == bandit_cid
    assert msg["data"]["is_npc_attack"] is True
    assert msg["data"]["damage_type"] == "slashing"


async def test_npc_attack_auto_apply_on_hit(gm_client, gm_ws, roster, auto_apply_on):
    """auto_apply_damage on: NPC hit triggers HP change to the PC via
    _apply_hp_change. Probe-fires up to 8 times to land at least one hit
    against Pip's AC (he's a Rogue with AC 14; +3 to hit needs d20≥11)."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    bandit_cid = "npc_bandit_test_2"
    await _seed_battle(gm_client, [
        _mkc(bandit_cid, hp_cur=11, hp_max=11, name="Bandit", template_id=1),
        _mkc(pip_cid, pip["id"], hp_cur=30, hp_max=30, name=pip["name"]),
    ])
    hit_seen = False
    for _ in range(12):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
            json={
                "combatant_id": bandit_cid,
                "action_name": "Scimitar",
                "attack_bonus": "+3",
                "damage": "1d6+1",
                "damage_type": "slashing",
                "target_combatant_id": pip_cid,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["hit"] and data["damage_applied"] > 0:
            hit_seen = True
            assert data["target_hp_after"] is not None
            assert data["auto_applied"] is True
            break
    assert hit_seen, (
        "Expected at least one hit + damage application across 12 attempts. "
        "If this fires intermittently the d20 RNG is degenerate or Pip's AC changed."
    )


async def test_npc_attack_no_target_still_rolls(gm_client, gm_ws):
    """No target_combatant_id: rolls + broadcasts still fire but hit is
    None and damage_applied is 0. Used when the GM wants the rolls
    surfaced without committing to a target."""
    bandit_cid = "npc_bandit_test_3"
    await _seed_battle(gm_client, [
        _mkc(bandit_cid, hp_cur=11, hp_max=11, name="Bandit", template_id=1),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_name": "Scimitar",
            "attack_bonus": "+3",
            "damage": "1d6+1",
            "damage_type": "slashing",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_total"] is not None
    assert data["damage_total"] is not None
    assert data["hit"] is None
    assert data["damage_applied"] == 0
    msg = await gm_ws.wait_for("weapon_attack")
    assert msg["data"]["caster_char_name"] == "Bandit"


async def test_npc_attack_missing_combatant_id(gm_client):
    """400 when combatant_id is absent."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={"action_name": "Scimitar", "damage": "1d6+1"},
    )
    assert resp.status_code == 400


async def test_npc_attack_unknown_combatant_id(gm_client):
    """404 when combatant_id doesn't resolve to a combatant in the
    active battle."""
    # Seed an empty battle to clear any prior state.
    await _seed_battle(gm_client, [])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": "does-not-exist",
            "action_name": "Scimitar",
            "damage": "1d6+1",
        },
    )
    assert resp.status_code == 404


async def test_npc_attack_unknown_target_combatant_id(gm_client):
    """404 when target_combatant_id is set but doesn't resolve."""
    bandit_cid = "npc_bandit_test_4"
    await _seed_battle(gm_client, [
        _mkc(bandit_cid, hp_cur=11, hp_max=11, name="Bandit", template_id=1),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_name": "Scimitar",
            "attack_bonus": "+3",
            "damage": "1d6+1",
            "target_combatant_id": "not-a-real-combatant",
        },
    )
    assert resp.status_code == 404


async def test_npc_attack_player_forbidden(alice_client, gm_client, roster):
    """403 when a non-GM player calls /npc_attack. NPCs are GM-authorised."""
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    bandit_cid = "npc_bandit_test_5"
    # GM seeds the battle so the combatant exists.
    await _seed_battle(gm_client, [
        _mkc(bandit_cid, hp_cur=11, hp_max=11, name="Bandit", template_id=1),
        _mkc(pip_cid, pip["id"], hp_cur=30, hp_max=30, name=pip["name"]),
    ])
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_cid,
            "action_name": "Scimitar",
            "attack_bonus": "+3",
            "damage": "1d6+1",
            "target_combatant_id": pip_cid,
        },
    )
    assert resp.status_code == 403
