"""v2.169.0 — /api/campaign/{cid}/set_in_lair + /trigger_lair_action —
Phase 3b of `docs/plans/legendary-actions.md`. The lair-action engine.

RAW MM p.11: while a creature is in its lair it takes a lair action on
initiative count 20 (losing ties). The GM drives it from the init-tracker.

Coverage:
  set_in_lair
    - happy: toggles in_lair + records lair_slug, broadcasts
      `in_lair_changed`, persists onto the battle-state dict.
    - 400 in_lair=true with no lair_slug.
    - 403 non-GM caller.
  trigger_lair_action
    - happy (damage, save-for-half): Magma Erupts (DEX DC 15, 6d6 fire,
      half) resolves each NPC target's save inline + applies damage +
      broadcasts `lair_action_resolved` with the action's RAW fields.
    - happy (condition): Tremor (DEX DC 15, no damage) installs prone on
      a failed save; broadcast carries effect=prone, damage="".
    - 409 not_in_lair when the battle's in_lair flag is False.
    - 409 unknown_lair_action for a bad action_id.
    - 400 missing action_id.
    - 403 non-GM caller.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, hp_cur=40, hp_max=40, name="X", initiative=10,
         token_template_id=None):
    c = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": initiative,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }
    if token_template_id is not None:
        c["token_template_id"] = token_template_id
    return c


async def _template_id_by_name(gm_client, name):
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert resp.status_code == 200, resp.text
    for t in resp.json():
        if t.get("name") == name:
            return t["id"]
    raise AssertionError(
        f"No {name!r} template in the demo seed. "
        f"Found: {[t.get('name') for t in resp.json()]}"
    )


@pytest_asyncio.fixture
async def bandit_template_id(gm_client):
    return await _template_id_by_name(gm_client, "Bandit")


async def _seed_battle(gm_client, combatants, *, turn_index=0, round=1,
                       in_lair=False, lair_slug="", last_lair_action_id="",
                       lair_acted_round=None):
    # last_lair_action_id + lair_acted_round are sent explicitly (defaults
    # ""/None) so the v2.172.0/v2.173.0 carry-forward guards don't leak the
    # no-repeat / once-per-round memory across tests — the guards only
    # preserve a key when the client omits it.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": turn_index,
            "round": round,
            "active": True,
            "in_lair": in_lair,
            "lair_slug": lair_slug,
            "last_lair_action_id": last_lair_action_id,
            "lair_acted_round": lair_acted_round,
        },
    )


# ── set_in_lair ──────────────────────────────────────────────────────────────


async def test_set_in_lair_toggles_flag_and_broadcasts(gm_client, gm_ws):
    await _seed_battle(gm_client, [
        _mkc("npc_lair_set_a", name="Filler", initiative=10),
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_in_lair",
        json={"in_lair": True, "lair_slug": "adult-red-dragon"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["in_lair"] is True
    assert data["lair_slug"] == "adult-red-dragon"

    msg = await gm_ws.wait_for("in_lair_changed")
    assert msg["data"]["in_lair"] is True
    assert msg["data"]["lair_slug"] == "adult-red-dragon"

    # Persisted onto the battle-state dict.
    bs = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")).json()["battle"]
    assert bs["in_lair"] is True
    assert bs["lair_slug"] == "adult-red-dragon"


async def test_set_in_lair_false_clears_slug(gm_client):
    await _seed_battle(gm_client, [
        _mkc("npc_lair_set_b", name="Filler", initiative=10),
    ], in_lair=True, lair_slug="adult-red-dragon")
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_in_lair",
        json={"in_lair": False, "lair_slug": "adult-red-dragon"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["lair_slug"] == ""


async def test_set_in_lair_requires_slug_400(gm_client):
    await _seed_battle(gm_client, [
        _mkc("npc_lair_set_c", name="Filler", initiative=10),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_in_lair",
        json={"in_lair": True},
    )
    assert resp.status_code == 400


async def test_set_in_lair_player_403(alice_client):
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_in_lair",
        json={"in_lair": True, "lair_slug": "adult-red-dragon"},
    )
    assert resp.status_code == 403


# ── trigger_lair_action ──────────────────────────────────────────────────────


async def test_trigger_magma_erupts_damage_save_for_half(
    gm_client, gm_ws, bandit_template_id,
):
    """Magma Erupts (DEX DC 15, 6d6 fire, save-for-half). Two bandit NPC
    targets resolve their DEX saves inline; the broadcast carries the
    RAW action fields."""
    b1 = "npc_lair_magma_b1"
    b2 = "npc_lair_magma_b2"
    await _seed_battle(gm_client, [
        _mkc(b1, hp_cur=40, hp_max=40, name="Bandit One", initiative=15,
             token_template_id=bandit_template_id),
        _mkc(b2, hp_cur=40, hp_max=40, name="Bandit Two", initiative=12,
             token_template_id=bandit_template_id),
    ], in_lair=True, lair_slug="adult-red-dragon")

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={
            "action_id": "magma-erupts",
            "aoe_target_combatant_ids": [b1, b2],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["action_name"] == "Magma Erupts"

    results = data["results"]
    ids = {r["combatant_id"] for r in results}
    assert ids == {b1, b2}, results
    for r in results:
        assert r["passed"] in (True, False), r  # NPCs resolve inline
        assert r["prompted"] is False
        assert isinstance(r["damage_dealt"], int)
        # Save-for-half: a failed save always takes damage.
        if r["passed"] is False:
            assert r["damage_dealt"] > 0, r

    msg = await gm_ws.wait_for("lair_action_resolved")
    assert msg["data"]["action_id"] == "magma-erupts"
    assert msg["data"]["save_ability"] == "DEX"
    assert msg["data"]["save_dc"] == 15
    assert msg["data"]["damage"] == "6d6"
    assert msg["data"]["damage_type"] == "fire"
    assert msg["data"]["half_on_save"] is True
    assert len(msg["data"]["results"]) == 2
    assert msg["data"]["last_lair_action_id"] == "magma-erupts"
    assert msg["data"]["lair_acted_round"] == 1


async def test_once_per_round_blocks_second_action(
    gm_client, bandit_template_id,
):
    """v2.173.0 — RAW MM p.11: one lair action per round. A second action
    in the same round (even a DIFFERENT one) → 409
    `lair_already_acted_this_round`."""
    b1 = "npc_lair_once_b1"
    combs = [_mkc(b1, hp_cur=40, hp_max=40, name="Bandit", initiative=15,
                  token_template_id=bandit_template_id)]
    await _seed_battle(gm_client, combs, round=1, in_lair=True,
                       lair_slug="adult-red-dragon")

    first = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "magma-erupts", "aoe_target_combatant_ids": [b1]},
    )
    assert first.status_code == 200, first.text
    assert first.json()["lair_acted_round"] == 1

    # A different action, still round 1 → blocked by once-per-round.
    second = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "tremor", "aoe_target_combatant_ids": [b1]},
    )
    assert second.status_code == 409
    body = second.json()
    assert body["error"] == "lair_already_acted_this_round"
    assert body["round"] == 1


async def test_once_per_round_override_succeeds(
    gm_client, bandit_template_id,
):
    """override=true bypasses the once-per-round gate."""
    b1 = "npc_lair_once_ovr_b1"
    combs = [_mkc(b1, hp_cur=40, hp_max=40, name="Bandit", initiative=15,
                  token_template_id=bandit_template_id)]
    await _seed_battle(gm_client, combs, round=1, in_lair=True,
                       lair_slug="adult-red-dragon")
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "magma-erupts", "aoe_target_combatant_ids": [b1]},
    )
    again = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "tremor", "aoe_target_combatant_ids": [b1],
              "override": True},
    )
    assert again.status_code == 200, again.text


async def test_next_round_frees_lair_action(
    gm_client, bandit_template_id,
):
    """When the round advances past the lair's last action, a fresh lair
    action is allowed again (one per round, not one per battle)."""
    b1 = "npc_lair_nextrnd_b1"
    combs = [_mkc(b1, hp_cur=40, hp_max=40, name="Bandit", initiative=15,
                  token_template_id=bandit_template_id)]
    # Pre-load: the lair acted (magma) in round 1; we're now in round 2.
    await _seed_battle(gm_client, combs, round=2, in_lair=True,
                       lair_slug="adult-red-dragon",
                       last_lair_action_id="magma-erupts", lair_acted_round=1)
    # A different action in the new round → allowed.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "tremor", "aoe_target_combatant_ids": [b1]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["lair_acted_round"] == 2


async def test_no_repeat_same_action_next_round_409(
    gm_client, bandit_template_id,
):
    """v2.172.0 — the same action two rounds in a row → 409
    `lair_action_repeated`. Pre-loaded into round 2 (so the once-per-round
    gate is clear) with magma as the previous round's action."""
    b1 = "npc_lair_norepeat_b1"
    combs = [_mkc(b1, hp_cur=40, hp_max=40, name="Bandit", initiative=15,
                  token_template_id=bandit_template_id)]
    await _seed_battle(gm_client, combs, round=2, in_lair=True,
                       lair_slug="adult-red-dragon",
                       last_lair_action_id="magma-erupts", lair_acted_round=1)
    repeat = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "magma-erupts", "aoe_target_combatant_ids": [b1]},
    )
    assert repeat.status_code == 409
    body = repeat.json()
    assert body["error"] == "lair_action_repeated"
    assert body["last_lair_action_id"] == "magma-erupts"


async def test_no_repeat_override_succeeds(
    gm_client, bandit_template_id,
):
    """The no-repeat guard is bypassable with override=true."""
    b1 = "npc_lair_norepeat_ovr_b1"
    combs = [_mkc(b1, hp_cur=40, hp_max=40, name="Bandit", initiative=15,
                  token_template_id=bandit_template_id)]
    await _seed_battle(gm_client, combs, round=2, in_lair=True,
                       lair_slug="adult-red-dragon",
                       last_lair_action_id="magma-erupts", lair_acted_round=1)
    again = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "magma-erupts", "aoe_target_combatant_ids": [b1],
              "override": True},
    )
    assert again.status_code == 200, again.text


async def test_set_in_lair_clears_lair_memory(gm_client, gm_ws,
                                              bandit_template_id):
    """Entering / leaving a lair resets BOTH the no-repeat memory and the
    once-per-round counter; the `in_lair_changed` broadcast carries the
    cleared values."""
    b1 = "npc_lair_reset_b1"
    combs = [_mkc(b1, hp_cur=40, hp_max=40, name="Bandit", initiative=15,
                  token_template_id=bandit_template_id)]
    await _seed_battle(gm_client, combs, round=1, in_lair=True,
                       lair_slug="adult-red-dragon")
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "magma-erupts", "aoe_target_combatant_ids": [b1]},
    )
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/set_in_lair",
        json={"in_lair": True, "lair_slug": "adult-red-dragon"},
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("in_lair_changed")
    assert msg["data"]["last_lair_action_id"] == ""
    assert msg["data"]["lair_acted_round"] is None
    # Magma fires cleanly now that both memories were reset.
    after = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "magma-erupts", "aoe_target_combatant_ids": [b1]},
    )
    assert after.status_code == 200, after.text


async def test_trigger_tremor_installs_prone_on_fail(
    gm_client, gm_ws, bandit_template_id,
):
    """Tremor (DEX DC 15, no damage, prone). NPC targets that fail the
    save get prone installed; the broadcast carries effect=prone."""
    b1 = "npc_lair_tremor_b1"
    await _seed_battle(gm_client, [
        _mkc(b1, hp_cur=40, hp_max=40, name="Bandit Prone", initiative=15,
             token_template_id=bandit_template_id),
    ], in_lair=True, lair_slug="adult-red-dragon")

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={
            "action_id": "tremor",
            "aoe_target_combatant_ids": [b1],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    r = data["results"][0]
    assert r["passed"] in (True, False), r
    assert r["damage_dealt"] == 0  # no damage on a non-damage action
    if r["passed"] is False:
        assert r["condition_installed"] is True, r

    msg = await gm_ws.wait_for("lair_action_resolved")
    assert msg["data"]["effect"] == "prone"
    assert msg["data"]["damage"] == ""
    assert msg["data"]["half_on_save"] is False


async def test_trigger_sand_cloud_installs_blinded_on_fail(
    gm_client, gm_ws, bandit_template_id,
):
    """v2.171.0 chromatic backfill — Blue Dragon Sand Cloud (CON DC 15, no
    damage, blinded). Exercises the new `blinded` condition template added
    to `_LAIR_ACTION_CONDITION_BUFFS`."""
    b1 = "npc_lair_sand_b1"
    await _seed_battle(gm_client, [
        _mkc(b1, hp_cur=40, hp_max=40, name="Bandit Blind", initiative=15,
             token_template_id=bandit_template_id),
    ], in_lair=True, lair_slug="adult-blue-dragon")

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={
            "action_id": "sand-cloud",
            "aoe_target_combatant_ids": [b1],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["action_name"] == "Sand Cloud"
    r = data["results"][0]
    assert r["passed"] in (True, False), r
    assert r["damage_dealt"] == 0
    if r["passed"] is False:
        assert r["condition_installed"] is True, r

    msg = await gm_ws.wait_for("lair_action_resolved")
    assert msg["data"]["action_id"] == "sand-cloud"
    assert msg["data"]["save_ability"] == "CON"
    assert msg["data"]["effect"] == "blinded"
    assert msg["data"]["damage"] == ""


async def test_trigger_lair_action_not_in_lair_409(
    gm_client, bandit_template_id,
):
    b1 = "npc_lair_notinlair_b1"
    await _seed_battle(gm_client, [
        _mkc(b1, hp_cur=40, hp_max=40, name="Bandit", initiative=15,
             token_template_id=bandit_template_id),
    ], in_lair=False)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "magma-erupts", "aoe_target_combatant_ids": [b1]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "not_in_lair"


async def test_trigger_lair_action_unknown_action_409(gm_client):
    await _seed_battle(gm_client, [
        _mkc("npc_lair_unknown", name="Filler", initiative=10),
    ], in_lair=True, lair_slug="adult-red-dragon")
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "no-such-action", "aoe_target_combatant_ids": []},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "unknown_lair_action"


async def test_trigger_lair_action_missing_action_id_400(gm_client):
    await _seed_battle(gm_client, [
        _mkc("npc_lair_missing", name="Filler", initiative=10),
    ], in_lair=True, lair_slug="adult-red-dragon")
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"aoe_target_combatant_ids": []},
    )
    assert resp.status_code == 400


async def test_trigger_lair_action_player_403(alice_client):
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "magma-erupts", "aoe_target_combatant_ids": []},
    )
    assert resp.status_code == 403


# ── v2.379.0 lair-condition closure — auto-install of unconscious /
# silenced / frightened previously needed GM narration. After v2.379.0
# the three keys are in _LAIR_ACTION_CONDITION_BUFFS so the engine
# auto-installs the buff on a failed save just like prone / blinded /
# restrained / charmed / poisoned. ───────────────────────────────────


async def test_trigger_slumberous_magic_installs_unconscious_on_fail(
    gm_client, gm_ws, bandit_template_id,
):
    """Brass Dragon Slumberous Magic (WIS DC 15, no damage, unconscious).
    Bandits have WIS save +0; a typical d20 roll fails DC 15 most of the
    time. On a fail, `unconscious` should auto-install."""
    b1 = "npc_lair_slumber_b1"
    await _seed_battle(gm_client, [
        _mkc(b1, hp_cur=40, hp_max=40, name="Bandit Asleep", initiative=15,
             token_template_id=bandit_template_id),
    ], in_lair=True, lair_slug="adult-brass-dragon")

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={
            "action_id": "slumberous-magic",
            "aoe_target_combatant_ids": [b1],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    r = data["results"][0]
    assert r["damage_dealt"] == 0
    if r["passed"] is False:
        assert r["condition_installed"] is True, r

    msg = await gm_ws.wait_for("lair_action_resolved")
    assert msg["data"]["effect"] == "unconscious"
    assert msg["data"]["damage"] == ""


async def test_trigger_memory_shred_installs_silenced_on_fail(
    gm_client, gm_ws, bandit_template_id,
):
    """Lich Memory Shred (WIS DC 18, no damage, silenced). On a failed
    save the `silenced` buff auto-installs (no-verbal-casting lock)."""
    b1 = "npc_lair_silence_b1"
    await _seed_battle(gm_client, [
        _mkc(b1, hp_cur=40, hp_max=40, name="Bandit Mute", initiative=15,
             token_template_id=bandit_template_id),
    ], in_lair=True, lair_slug="lich")

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={
            "action_id": "memory-shred",
            "aoe_target_combatant_ids": [b1],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    r = data["results"][0]
    assert r["damage_dealt"] == 0
    if r["passed"] is False:
        assert r["condition_installed"] is True, r

    msg = await gm_ws.wait_for("lair_action_resolved")
    assert msg["data"]["effect"] == "silenced"
    assert msg["data"]["damage"] == ""
    assert msg["data"]["save_ability"] == "WIS"


async def test_trigger_shimmering_visions_installs_frightened_on_fail(
    gm_client, gm_ws, bandit_template_id,
):
    """Gold Dragon Shimmering Visions (WIS DC 15, no damage, frightened).
    On a failed save the `frightened` buff auto-installs."""
    b1 = "npc_lair_fear_b1"
    await _seed_battle(gm_client, [
        _mkc(b1, hp_cur=40, hp_max=40, name="Bandit Afraid", initiative=15,
             token_template_id=bandit_template_id),
    ], in_lair=True, lair_slug="adult-gold-dragon")

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={
            "action_id": "shimmering-visions",
            "aoe_target_combatant_ids": [b1],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    r = data["results"][0]
    assert r["damage_dealt"] == 0
    if r["passed"] is False:
        assert r["condition_installed"] is True, r

    msg = await gm_ws.wait_for("lair_action_resolved")
    assert msg["data"]["effect"] == "frightened"
    assert msg["data"]["damage"] == ""


async def test_lair_action_resolved_carries_owner_name(
    gm_client, gm_ws, bandit_template_id,
):
    """v2.177.0 — the `lair_action_resolved` broadcast (and response)
    carries `owner_name`, the lair owner's display name, so the roll-log
    card is self-contained on reload. Resolved from the combatant whose
    `lair_slug` matches the battle's lair."""
    dragon = {
        "id": "npc_lair_owner_dragon", "char_id": None,
        "token_template_id": None, "name": "Ancient Red Dragon",
        "initiative": 20, "hp_current": 546, "hp_max": 546, "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        "lair_slug": "adult-red-dragon",
        "lair_actions": [{"id": "magma-erupts", "name": "Magma Erupts"}],
    }
    b1 = "npc_lair_owner_b1"
    await _seed_battle(gm_client, [
        dragon,
        _mkc(b1, hp_cur=40, hp_max=40, name="Bandit", initiative=15,
             token_template_id=bandit_template_id),
    ], in_lair=True, lair_slug="adult-red-dragon")

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/trigger_lair_action",
        json={"action_id": "magma-erupts", "aoe_target_combatant_ids": [b1]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["owner_name"] == "Ancient Red Dragon"

    msg = await gm_ws.wait_for("lair_action_resolved")
    assert msg["data"]["owner_name"] == "Ancient Red Dragon"
