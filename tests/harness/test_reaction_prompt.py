"""v2.67.0 — Phase 1 of the reactions-automation plan.

Server-side foundation: ``reaction_prompt`` WS broadcast type +
``/api/campaign/{cid}/use_reaction`` endpoint + retrofit of the
OA exit-reach trigger to emit a prompt alongside the legacy
``feature_used`` advisory.

See ``docs/plans/reactions-automation.md`` for the full design.

Coverage:
  - Token move that exits a watcher's reach → ``reaction_prompt``
    broadcast fires with a ``take-the-oa`` option + the legacy
    ``feature_used(source="opportunity-attack-trigger")`` still
    fires (backward compat).
  - POST /use_reaction with the prompt_id + ``reaction_key=take-the-oa``
    → 200 + ``reaction_prompt_resolved`` broadcast + watcher's
    ``economy.reaction`` flips to True.
  - Replay guard: second POST with the same prompt_id returns 409
    ``prompt_already_resolved``.
  - Missing prompt_id → 400.
  - Unknown reaction_key → 400.
  - Unknown prompt_id → 409 ``prompt_expired_or_unknown``.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _make_combatant(name, char_id, init=10, hp=40):
    return {
        "id": f"tok_rxn_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {
            "action": False, "bonus": False,
            "reaction": False, "movement": 0,
        },
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )


async def _place_token(gm_client, char_id: int, x: float, y: float):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _get_token_for_char(gm_client, char_id: int):
    resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert resp.status_code == 200
    for t in resp.json().get("tokens", []):
        if t.get("character_id") == char_id:
            return t
    return None


def _prompt_broadcasts(gm_ws) -> list:
    return list(gm_ws.buffered("reaction_prompt"))


def _resolved_broadcasts(gm_ws) -> list:
    return list(gm_ws.buffered("reaction_prompt_resolved"))


async def test_oa_exit_reach_emits_reaction_prompt(
    gm_client, gm_ws, roster,
):
    """Krieger leaves Tavik's 5 ft reach → reaction_prompt broadcast
    fires with a take-the-oa option AND the legacy feature_used
    broadcast still fires for backward compat.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])

    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok, "Krieger token must exist"
    await asyncio.sleep(0.15)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0},
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)

    # New reaction_prompt broadcast.
    prompts = _prompt_broadcasts(gm_ws)
    matching = [
        m for m in prompts
        if (m.get("data") or {}).get("watcher_char_id") == tavik["id"]
        and (m.get("data") or {}).get("trigger_event")
        == "creature_exits_reach"
    ]
    assert matching, (
        f"expected reaction_prompt(creature_exits_reach) naming Tavik; "
        f"buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in prompts]}"
    )
    data = matching[0]["data"]
    assert isinstance(data.get("prompt_id"), str) and data["prompt_id"].startswith("rxn_")
    keys = [o.get("key") for o in (data.get("options") or [])]
    assert "take-the-oa" in keys, (
        f"expected take-the-oa option; got options={data.get('options')}"
    )
    # target_user_ids should include the GM (NPC owners aren't tested
    # here — Tavik is owned by the GM in the demo).
    assert isinstance(data.get("target_user_ids"), list)
    assert len(data["target_user_ids"]) >= 1

    # Backward compat: legacy feature_used advisory still fires.
    legacy = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "opportunity-attack-trigger"
        and (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert legacy, "legacy feature_used advisory should still fire"


async def test_use_reaction_marks_economy_and_resolves_prompt(
    gm_client, gm_ws, roster,
):
    """End-to-end Phase 1 flow: move provokes OA → reaction_prompt
    fires → POST /use_reaction with the prompt_id → 200 +
    reaction_prompt_resolved broadcast + Tavik's economy.reaction
    flips to True.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0},
    )
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == tavik["id"]
    ]
    assert prompts
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "take-the-oa",
            "watcher_char_id": tavik["id"],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["reaction_key"] == "take-the-oa"
    assert data["trigger_event"] == "creature_exits_reach"

    await asyncio.sleep(0.2)
    resolved = _resolved_broadcasts(gm_ws)
    matching = [
        m for m in resolved
        if (m.get("data") or {}).get("prompt_id") == prompt_id
    ]
    assert matching, (
        f"expected reaction_prompt_resolved with prompt_id={prompt_id}"
    )

    # economy_update broadcast for Tavik's reaction flip.
    econ_msgs = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == tavik["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ_msgs, (
        f"expected economy_update for Tavik's reaction slot; "
        f"buffered: {[(m.get('data') or {}).get('slot') for m in gm_ws.buffered('economy_update')]}"
    )
    assert econ_msgs[-1]["data"]["used"] is True


async def test_use_reaction_replay_guard(
    gm_client, gm_ws, roster,
):
    """Second POST with the same prompt_id returns 409."""
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0},
    )
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == tavik["id"]
    ]
    prompt_id = prompts[0]["data"]["prompt_id"]

    first = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "take-the-oa",
            "watcher_char_id": tavik["id"],
        },
    )
    assert first.status_code == 200

    second = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "take-the-oa",
            "watcher_char_id": tavik["id"],
        },
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert body.get("error") == "prompt_already_resolved"


async def test_use_reaction_unknown_prompt_id(gm_client):
    """409 prompt_expired_or_unknown when the prompt_id was never
    issued (or has expired)."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": "rxn_nonexistent",
            "reaction_key": "take-the-oa",
            "watcher_char_id": 1,
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "prompt_expired_or_unknown"


async def test_use_reaction_missing_prompt_id(gm_client):
    """400 when prompt_id is missing entirely."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "reaction_key": "take-the-oa",
            "watcher_char_id": 1,
        },
    )
    assert resp.status_code == 400, resp.text
