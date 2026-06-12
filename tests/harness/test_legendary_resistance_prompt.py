"""v2.166.0 — Phase 2b of `docs/plans/legendary-actions.md`: deferred
legendary-resistance prompts.

When an NPC with a legendary-resistance charge left FAILS a feature save
that would impose a condition, the save-resolver does NOT install the
condition. Instead it defers the effect and broadcasts a
``legendary_resistance_prompt`` so the GM can choose (RAW MM p.11: "If
the creature fails a saving throw, it can choose to succeed instead"):

  - spend a charge  → ``/spend_legendary_resistance`` with the prompt_id
    flips the save to a success (no condition installs, pool decrements,
    ``legendary_resistance_resolved`` with ``passed=True``).
  - decline         → ``/decline_legendary_resistance`` applies the held
    condition (``legendary_resistance_resolved`` with ``passed=False``,
    ``condition_installed=True``).

The trigger here is the Battle Master's Menacing Attack (DC 16 WIS save →
Frightened) aimed at an Adult Red Dragon (WIS save +6, Legendary
Resistance 3/Day). NPC saves are random, so each test loops until a fail
lands the deferred prompt — mirroring ``test_menacing_attack``'s
fail-until-installed loops.
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


async def _template_id_by_name(gm_client, name):
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert resp.status_code == 200, resp.text
    for t in resp.json():
        if t.get("name") == name:
            return t["id"]
    raise AssertionError(f"No {name!r} template in the demo seed")


@pytest_asyncio.fixture
async def adult_red_dragon_template_id(gm_client):
    return await _template_id_by_name(gm_client, "Adult Red Dragon")


@pytest_asyncio.fixture
async def garrik_battle_master(gm_client, roster):
    """PATCH Garrik to Battle Master + a deep superiority-dice pool."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {
            "subclass": "Battle Master",
            "superiority_die_size": "d8",
            "resources": [_superiority_dice_block(60, 60)],
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


async def _seed_battle(gm_client, garrik, dragon_cid, dragon_tmpl):
    garrik_tok = f"tok_lrp_garrik_{garrik['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": garrik_tok, "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 20, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": dragon_cid, "char_id": None,
             "token_template_id": dragon_tmpl, "name": "Adult Red Dragon",
             "initiative": 10, "hp_current": 256, "hp_max": 256, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _menace_until_prompt(gm_client, gm_ws, garrik, dragon_cid):
    """Swing Menacing Attack at the dragon until a failed WIS save defers
    to a legendary-resistance prompt. Returns the prompt broadcast data."""
    for _ in range(60):
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_menacing_attack",
            json={"character_id": garrik["id"],
                  "target_combatant_id": dragon_cid},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["save_resolved"] is True, data
        # Deferred fail: the endpoint reports the fail but NOTHING installs.
        if data["save_passed"] is False:
            assert data["condition_installed"] is False, data
            await asyncio.sleep(0.1)
            prompts = gm_ws.buffered("legendary_resistance_prompt")
            assert prompts, (
                "failed save did not broadcast a legendary_resistance_prompt"
            )
            return prompts[0]["data"]
    raise AssertionError("no failed dragon WIS save in 60 swings")


async def _dragon_buffs(gm_client, dragon_cid):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    assert r.status_code == 200, r.text
    state = r.json().get("battle") or {}
    dragon = next(
        (c for c in (state.get("combatants") or []) if c.get("id") == dragon_cid),
        None,
    )
    assert dragon is not None, "dragon vanished from battle state"
    return dragon.get("buffs") or []


async def test_failed_save_defers_then_spend_flips_to_success(
    gm_client, gm_ws, garrik_battle_master, adult_red_dragon_template_id,
):
    """A failed WIS save defers to a prompt; spending a charge flips the
    save to a success — no Frightened installs, pool drops 3 → 2."""
    garrik = garrik_battle_master
    dragon_cid = "npc_lrp_spend"
    await _seed_battle(gm_client, garrik, dragon_cid, adult_red_dragon_template_id)

    prompt = await _menace_until_prompt(gm_client, gm_ws, garrik, dragon_cid)
    assert prompt["combatant_id"] == dragon_cid
    assert prompt["combatant_name"] == "Adult Red Dragon"
    assert prompt["save_ability"] == "WIS"
    assert prompt["save_dc"] == 16
    assert prompt["condition_key"] == "frightened"
    assert prompt["current"] == 3
    assert prompt["max"] == 3
    prompt_id = prompt["prompt_id"]
    assert prompt_id

    # Nothing installed while the prompt is pending.
    assert not any(
        (b or {}).get("key") == "frightened"
        for b in await _dragon_buffs(gm_client, dragon_cid)
    )

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_legendary_resistance",
        json={"prompt_id": prompt_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["combatant_id"] == dragon_cid
    assert body["resolution"] == "spent"
    assert body["max"] == 3
    assert body["current"] == 2  # 3 → 2

    resolved = await gm_ws.wait_for("legendary_resistance_resolved")
    assert resolved["data"]["prompt_id"] == prompt_id
    assert resolved["data"]["passed"] is True
    assert resolved["data"]["condition_installed"] is False
    assert resolved["data"]["reason"] == "spent"

    # The save flipped to a success → still no Frightened on the dragon.
    assert not any(
        (b or {}).get("key") == "frightened"
        for b in await _dragon_buffs(gm_client, dragon_cid)
    )

    # The prompt is single-use — replaying it 404s.
    replay = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_legendary_resistance",
        json={"prompt_id": prompt_id},
    )
    assert replay.status_code == 404


async def test_failed_save_decline_installs_held_condition(
    gm_client, gm_ws, garrik_battle_master, adult_red_dragon_template_id,
):
    """Declining the prompt lets the failed save stand — the held
    Frightened installs on the dragon, no charge spent."""
    garrik = garrik_battle_master
    dragon_cid = "npc_lrp_decline"
    await _seed_battle(gm_client, garrik, dragon_cid, adult_red_dragon_template_id)

    prompt = await _menace_until_prompt(gm_client, gm_ws, garrik, dragon_cid)
    prompt_id = prompt["prompt_id"]
    assert prompt_id

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/decline_legendary_resistance",
        json={"prompt_id": prompt_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["resolution"] == "declined"
    assert body["condition_installed"] is True
    assert body["condition_key"] == "frightened"

    resolved = await gm_ws.wait_for("legendary_resistance_resolved")
    assert resolved["data"]["prompt_id"] == prompt_id
    assert resolved["data"]["passed"] is False
    assert resolved["data"]["condition_installed"] is True
    assert resolved["data"]["reason"] == "declined"

    frightened = next(
        (b for b in await _dragon_buffs(gm_client, dragon_cid)
         if (b or {}).get("key") == "frightened"), None)
    assert frightened is not None, "decline did not install Frightened"
    assert frightened.get("source_char_id") == garrik["id"]

    # Declining spent no charge — replaying the prompt 404s (consumed).
    replay = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/decline_legendary_resistance",
        json={"prompt_id": prompt_id},
    )
    assert replay.status_code == 404


async def test_spend_unknown_prompt_404(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_legendary_resistance",
        json={"prompt_id": "deadbeefcafe"},
    )
    assert resp.status_code == 404


async def test_decline_unknown_prompt_404(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/decline_legendary_resistance",
        json={"prompt_id": "deadbeefcafe"},
    )
    assert resp.status_code == 404


async def test_decline_missing_prompt_id_400(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/decline_legendary_resistance",
        json={},
    )
    assert resp.status_code == 400


async def test_decline_player_caller_403(alice_client):
    """Non-GM players cannot resolve an NPC's legendary-resistance prompt."""
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/decline_legendary_resistance",
        json={"prompt_id": "deadbeefcafe"},
    )
    assert resp.status_code == 403
