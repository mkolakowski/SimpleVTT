"""v2.99.253 — Battle Master maneuver 3: Menacing Attack.

Phase E.1 Phase 3 (maneuver 3 of 16). RAW PHB p.74: on hit,
expend 1 superiority die; +die damage and target makes a WIS
save DC 8 + prof + max(STR, DEX) or be Frightened of attacker
until end of attacker's next turn.

Mirrors Trip / Disarming Attack but the save ability is WIS
and the on-fail effect is Frightened.

Garrik is the fixture. Tests PATCH his subclass to "Battle
Master" + seed superiority-dice.

Tests:
  - Happy d8 → extra 1..8, DC 16, save_ability WIS, dice 4→3.
  - Out of dice → 409.
  - Wrong subclass → 409.
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


def _ma_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "menacing-attack"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _superiority_dice_block(current: int, maximum: int) -> dict:
    return {
        "key": "superiority-dice",
        "name": "Superiority Dice",
        "current": current, "max": maximum, "reset": "short",
        "source": "fighter Lv 3 / Combat Superiority",
        "class_slug": "fighter",
        "desc": "Battle Master maneuvers. Refreshes on short or long rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def garrik_battle_master(gm_client, roster):
    """PATCH Garrik to Battle Master + seed superiority-dice."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {
            "subclass": "Battle Master",
            "superiority_die_size": "d8",
            "resources": [_superiority_dice_block(4, 4)],
        },
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "resources": []},
            class_slug="fighter",
        )


async def test_use_ma_happy(
    gm_client, gm_ws, garrik_battle_master,
):
    """Lv 9 Garrik d8 → extra in 1..8, DC 16, WIS, dice 4→3."""
    garrik = garrik_battle_master
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["die_size"] == "d8"
    assert 1 <= data["extra_damage"] <= 8
    assert data["save_dc"] == 16
    assert data["save_ability"] == "WIS"
    assert data["dice_remaining"] == 3
    await asyncio.sleep(0.3)
    feats = _ma_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_ma_out_of_dice(
    gm_client, garrik_battle_master,
):
    """current=0 → 409."""
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(0, 4)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_ma_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_ma_resolves_npc_save_installs_frightened(
    gm_client, gm_ws, garrik_battle_master,
):
    """v2.99.406 — Phase 3.1: against an NPC target, Menacing Attack
    auto-resolves the WIS save server-side (_resolve_feature_save) and
    installs Frightened on a fail.

    NPC saves are random, so loop until a fail lands — Garrik's DC 16 vs
    a Bandit's +0 WIS fails ~75% of swings. Seed a deep die pool up front
    so each iteration is just one POST. Asserts both branches as they
    occur: on a pass nothing installs; on a fail the `frightened` buff
    lands on the dummy (verified via battle_update).
    """
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(40, 40)]},
    )
    tmpl_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = tmpl_resp.json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )

    garrik_tok = f"tok_ma_garrik_{garrik['id']}"
    dummy_tok = "tok_ma_bandit"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": garrik_tok, "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": dummy_tok, "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )

    landed = False
    for _ in range(40):
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
            json={"character_id": garrik["id"],
                  "target_combatant_id": dummy_tok},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["save_resolved"] is True, data
        if data["save_passed"]:
            assert data["condition_installed"] is False
            continue
        # Failed save → Frightened installs.
        assert data["condition_installed"] is True
        bu = await gm_ws.wait_for("battle_update")
        dummy_cb = next(
            (c for c in (bu["data"].get("combatants") or [])
             if c.get("id") == dummy_tok), None)
        assert dummy_cb is not None
        frightened = next(
            (b for b in (dummy_cb.get("buffs") or [])
             if (b or {}).get("key") == "frightened"), None)
        assert frightened is not None, dummy_cb.get("buffs")
        assert frightened.get("source_char_id") == garrik["id"]
        assert frightened.get("name") == "Frightened (Menacing Attack)"
        landed = True
        break

    assert landed, "no failed WIS save in 40 tries; Frightened didn't install"


async def test_ma_resolves_pc_save_installs_frightened(
    gm_client, roster, garrik_battle_master,
):
    """v2.99.407 — Phase 3.2: against a PC target, Menacing Attack prompts
    the player via a roll-request and installs Frightened when they fail
    on /respond — sharing the spell save-or-suck install path.

    Loop until the PC fails the WIS save (DC 16). Assert: the endpoint
    reports save_prompted with a prompt id; /respond installs the
    `frightened` buff on a fail; and — because Menacing Attack passes
    repeated_save=False — the installed buff carries NO repeated-save
    stamp (it just expires, it isn't shrugged off at end of turn).
    """
    garrik = garrik_battle_master
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(40, 40)]},
    )

    garrik_tok = f"tok_mapc_garrik_{garrik['id']}"
    pip_tok = f"tok_mapc_pip_{pip['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": garrik_tok, "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": pip_tok, "char_id": pip["id"], "name": pip["name"],
             "initiative": 8, "hp_current": 40, "hp_max": 40, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )

    landed = False
    for _ in range(40):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": pip["id"], "key": "frightened"},
        )
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
            json={"character_id": garrik["id"], "target_combatant_id": pip_tok},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["save_prompted"] is True, data
        assert data["save_passed"] is None  # deferred to /respond
        prompt_id = data["save_prompt_id"]
        assert prompt_id

        rr = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": pip["id"]},
        )
        assert rr.status_code == 200, rr.text
        if rr.json().get("auto_buff_installed") == "Frightened (Menacing Attack)":
            landed = True
            break

    assert landed, "no failed PC WIS save in 40 tries; Frightened didn't install"

    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    frightened = next(
        (b for b in buffs if (b or {}).get("key") == "frightened"), None)
    assert frightened is not None, buffs
    assert frightened.get("name") == "Frightened (Menacing Attack)"
    assert frightened.get("source_char_id") == garrik["id"]
    # repeated_save=False → no end-of-turn re-save stamp (fixed duration).
    assert not frightened.get("repeated_save_ability")
    assert int(frightened.get("repeated_save_dc") or 0) == 0


async def test_ma_armed_rider_fires_save_on_hit(
    gm_client, gm_ws, garrik_battle_master,
):
    """v2.99.408 — Phase 3.3: calling Menacing Attack with NO target ARMS
    an on-hit rider; the next weapon hit auto-adds the superiority die to
    damage AND fires the WIS save via _fire_weapon_hit_saves.

    Arms once, then attacks an NPC bandit until a swing lands (misses
    don't consume a once-per-turn rider). On the hit asserts: the
    `menacing-attack` +1d8 damage uplift rode, and `feature_saves` reports
    the WIS DC-16 save fired against the target.
    """
    garrik = garrik_battle_master
    await _patch_sheet(
        gm_client, garrik["id"],
        {"resources": [_superiority_dice_block(40, 40)]},
    )
    tmpl_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = tmpl_resp.json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    garrik_tok = f"tok_maarm_garrik_{garrik['id']}"
    dummy_tok = "tok_maarm_bandit"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": garrik_tok, "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": dummy_tok, "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )

    # Arm the maneuver (no target) → installs the on-hit rider.
    gm_ws.mark()
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
        json={"character_id": garrik["id"]},
    )
    assert arm.status_code == 200, arm.text
    assert arm.json()["buff_installed"] is True

    bu = await gm_ws.wait_for("buff_update")
    rider = next((b for b in bu["data"]["buffs"]
                  if b.get("key") == "menacing-attack"), None)
    assert rider is not None, bu["data"]["buffs"]
    eff = rider.get("effects") or {}
    assert eff.get("weapon_hit_bonus_dice") == "1d8"
    assert eff.get("weapon_hit_once_per_turn") is True
    assert eff.get("weapon_hit_flag") == "menacing_attack"
    spec = eff.get("weapon_hit_save") or {}
    assert spec.get("save_ability") == "WIS"
    assert spec.get("dc") == 16
    assert (spec.get("condition_buff") or {}).get("key") == "frightened"

    # Attack until a swing connects; the rider fires on that hit.
    fired = None
    for _ in range(25):
        a = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": garrik["id"], "attack_index": 0,
                  "target_combatant_id": dummy_tok, "override": True},
        )
        assert a.status_code == 200, a.text
        ad = a.json()
        if ad["hit"]:
            fired = ad
            break
    assert fired is not None, "no hit in 25 swings"

    # The superiority die rode the damage as a menacing-attack uplift.
    ups = [u for u in (fired.get("auto_uplifts") or [])
           if u.get("source") == "menacing-attack"]
    assert len(ups) == 1, fired.get("auto_uplifts")
    assert ups[0]["expression"] == "1d8"
    # The WIS save fired against the target on the hit.
    fs = [s for s in (fired.get("feature_saves") or [])
          if s.get("resolved") and s.get("source") == "menacing-attack"]
    assert len(fs) == 1, fired.get("feature_saves")
    assert fs[0]["save_ability"] == "WIS"
    assert fs[0]["save_dc"] == 16
    assert fs[0]["target_combatant_id"] == dummy_tok
