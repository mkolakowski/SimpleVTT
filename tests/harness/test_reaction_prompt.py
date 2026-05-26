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


# ── Phase 1b — per-user reaction_prompt_mode setting ──


async def test_reaction_prompt_mode_setting_valid(gm_client):
    """v2.67.1 — /api/settings/reaction_prompt_mode persists the
    user's prompt-UX preference. Accepts the three valid values."""
    for mode in ("popup", "roll_log_only", "off"):
        resp = await gm_client.post(
            "/api/settings/reaction_prompt_mode",
            json={"mode": mode},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["reaction_prompt_mode"] == mode
    # Restore default so subsequent tests see "popup".
    await gm_client.post(
        "/api/settings/reaction_prompt_mode", json={"mode": "popup"},
    )


async def test_reaction_prompt_mode_setting_invalid(gm_client):
    """400 when the mode is not in the allowed set."""
    resp = await gm_client.post(
        "/api/settings/reaction_prompt_mode",
        json={"mode": "spam-the-popup"},
    )
    assert resp.status_code == 400, resp.text


# ── v2.67.2 — Phase 2a: Uncanny Dodge prompt announcement ──


async def test_uncanny_dodge_emits_reaction_prompt(
    gm_client, gm_ws, roster,
):
    """v2.67.2 — after v2.49.243 auto-fires Uncanny Dodge on Pip (Rogue
    Lv 5+), the new prompt pipeline emits a `reaction_prompt(
    trigger_event="damage_taken")` ack so the popup + roll-log UX
    captures it. The option key is `uncanny-dodge-ack`.

    Legacy auto-fire behavior is unchanged (damage halved, reaction
    marked, feature_used broadcast still fires) — this test only
    asserts the new prompt is emitted alongside.
    """
    pip = roster["Pip Quickfingers"]

    # Force auto_apply_damage on so _apply_damage_to_combatant runs.
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
        "auto_apply_damage": "on",
    }
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings",
        data=form, follow_redirects=False,
    )
    try:
        pip_cid = f"tok_ud_{pip['id']}"
        bandit_cid = "npc_bandit_ud_prompt"
        await _seed_battle(gm_client, [
            {
                "id": bandit_cid,
                "char_id": None,
                "token_template_id": 1,
                "name": "Bandit",
                "initiative": 12,
                "hp_current": 11, "hp_max": 11,
                "buffs": [],
                "economy": {
                    "action": False, "bonus": False,
                    "reaction": False, "movement": 0,
                },
            },
            {
                "id": pip_cid,
                "char_id": pip["id"],
                "name": pip["name"],
                "initiative": 10,
                "hp_current": 33, "hp_max": 33,
                "buffs": [],
                "economy": {
                    "action": False, "bonus": False,
                    "reaction": False, "movement": 0,
                },
            },
        ])
        await asyncio.sleep(0.15)
        gm_ws.mark()

        # Probe until a hit lands. Flat +10 attack + flat 6 damage
        # always hits Pip's AC and applies 3 (UD halves 6 → 3).
        landed = None
        for _ in range(20):
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
                json={
                    "combatant_id": bandit_cid,
                    "action_name": "Greatclub",
                    "attack_bonus": "+10",
                    "damage": "6",
                    "damage_type": "bludgeoning",
                    "target_combatant_id": pip_cid,
                },
            )
            assert r.status_code == 200, r.text
            data = r.json()
            if data.get("hit") and data.get("damage_applied", 0) > 0:
                landed = data
                break
        assert landed, "expected at least one hit in 20 swings"
        # UD halved 6 → 3.
        assert landed["damage_applied"] == 3

        # New prompt fired alongside the legacy feature_used advisory.
        await asyncio.sleep(0.2)
        prompts = _prompt_broadcasts(gm_ws)
        matching = [
            m for m in prompts
            if (m.get("data") or {}).get("watcher_char_id") == pip["id"]
            and (m.get("data") or {}).get("trigger_event")
            == "damage_taken"
        ]
        assert matching, (
            f"expected reaction_prompt(damage_taken) for Pip; "
            f"buffered prompts: "
            f"{[(m.get('data') or {}).get('trigger_event') for m in prompts]}"
        )
        keys = [
            o.get("key")
            for o in matching[0]["data"].get("options", [])
        ]
        assert "uncanny-dodge-ack" in keys, (
            f"expected uncanny-dodge-ack option; got {keys}"
        )

        # Ack the prompt — should resolve cleanly without changing
        # state (legacy auto-fire already did the work).
        prompt_id = matching[0]["data"]["prompt_id"]
        gm_ws.mark()
        ack = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
            json={
                "prompt_id": prompt_id,
                "reaction_key": "uncanny-dodge-ack",
                "watcher_char_id": pip["id"],
            },
        )
        assert ack.status_code == 200, ack.text
        await asyncio.sleep(0.15)
        resolved = _resolved_broadcasts(gm_ws)
        assert any(
            (m.get("data") or {}).get("prompt_id") == prompt_id
            for m in resolved
        ), "expected reaction_prompt_resolved broadcast"
    finally:
        # Restore auto_apply_damage = off.
        form["auto_apply_damage"] = ""
        del form["auto_apply_damage"]
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings",
            data=form, follow_redirects=False,
        )


# ── v2.68.5 — Phase 2b: Cutting Words + Indomitable prompt ack ──


async def test_cutting_words_emits_reaction_prompt(
    gm_client, gm_ws, roster,
):
    """v2.68.5 — `/use_cutting_words` (v2.54.0) now ALSO emits a
    `reaction_prompt(reaction_used)` ack alongside its existing
    `feature_used` advisory so the popup + roll-log UX captures it.
    Lyra is the demo's Bard Lv 7 (College of Lore) with a 1d8 BI die.
    """
    lyra = roster["Lyra Sunstrider"]
    # Long rest so BI uses are full.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=12, hp=40),
    ])
    await asyncio.sleep(0.1)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_cutting_words",
        json={"character_id": lyra["id"]},
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == lyra["id"]
        and (m.get("data") or {}).get("trigger_event") == "reaction_used"
    ]
    assert prompts, (
        f"expected reaction_prompt(reaction_used) for Lyra after "
        f"Cutting Words; buffered prompts: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    keys = [o.get("key") for o in prompts[0]["data"].get("options", [])]
    assert "cutting-words-ack" in keys, (
        f"expected cutting-words-ack option; got {keys}"
    )

    # Ack resolves cleanly.
    prompt_id = prompts[0]["data"]["prompt_id"]
    ack = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "cutting-words-ack",
            "watcher_char_id": lyra["id"],
        },
    )
    assert ack.status_code == 200, ack.text


async def test_indomitable_emits_reaction_prompt(
    gm_client, gm_ws, roster,
):
    """v2.68.5 — `/use_indomitable` (v2.56.0) now ALSO emits a
    `reaction_prompt(reaction_used)` ack alongside its existing
    `feature_used` advisory. Garrik is the demo's Fighter Lv 9.
    """
    garrik = roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )
    await _seed_battle(gm_client, [
        _make_combatant(garrik["name"], garrik["id"], init=12, hp=85),
    ])
    await asyncio.sleep(0.1)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable",
        json={"character_id": garrik["id"]},
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == garrik["id"]
        and (m.get("data") or {}).get("trigger_event") == "reaction_used"
    ]
    assert prompts, (
        f"expected reaction_prompt(reaction_used) for Garrik after "
        f"Indomitable arm; buffered prompts: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    keys = [o.get("key") for o in prompts[0]["data"].get("options", [])]
    assert "indomitable-ack" in keys, (
        f"expected indomitable-ack option; got {keys}"
    )

    prompt_id = prompts[0]["data"]["prompt_id"]
    ack = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "indomitable-ack",
            "watcher_char_id": garrik["id"],
        },
    )
    assert ack.status_code == 200, ack.text


# ── v2.67.3 — NPC reaction slot consumption ──


async def test_use_reaction_marks_npc_economy_via_combatant_id(
    gm_client, gm_ws, roster,
):
    """v2.67.3 — When a Krieger (PC) moves out of an NPC bandit's
    reach, the OA prompt fires for the bandit (NPC watcher). GM
    clicks "Take the OA" → POST /use_reaction with the prompt_id
    (no watcher_char_id since NPCs don't have one) → server flips
    the bandit's reaction chip via the new combatant_id-keyed
    helper and broadcasts an economy_update.
    """
    krieger = roster["Krieger Stonefist"]

    # Create a bandit NPC token at (350, 350).
    tmpl_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/templates",
        json={
            "name": "Bandit (NPC OA test)",
            "template": "dnd5e",
            "tags": ["npc", "harness"],
            "sheet": {"monster_slug": "bandit"},
        },
    )
    assert tmpl_resp.status_code == 200, tmpl_resp.text
    tmpl = tmpl_resp.json()
    tok_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={
            "token_template_id": tmpl["id"],
            "label": "Bandit",
            "x": 350.0, "y": 350.0,
            "color": "#a23030", "size": 1,
        },
    )
    assert tok_resp.status_code == 200, tok_resp.text
    bandit_tok = tok_resp.json()

    bandit_cid = "tok_npc_oa_bandit"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        {
            "id": bandit_cid,
            "char_id": None,
            "source_token_id": bandit_tok["id"],
            "token_template_id": tmpl["id"],
            "name": "Bandit",
            "initiative": 8,
            "hp_current": 11, "hp_max": 11,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])

    # Krieger 5 ft east of the bandit, then moves 25 ft → 30 ft.
    await _place_token(gm_client, krieger["id"], 420.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Move Krieger out of the bandit's 5 ft reach.
    move = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0},
    )
    assert move.status_code == 200, move.text
    await asyncio.sleep(0.2)

    # Find the bandit's OA prompt.
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_combatant_id") == bandit_cid
    ]
    assert prompts, (
        f"expected OA prompt for the bandit; got "
        f"{[(m.get('data') or {}).get('watcher_combatant_id') for m in _prompt_broadcasts(gm_ws)]}"
    )
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    # GM resolves the NPC reaction. watcher_char_id intentionally
    # omitted — NPCs don't have one.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "take-the-oa",
        },
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    # economy_update broadcast on the bandit's combatant_id with
    # slot=reaction + used=true. Note the new payload field
    # `combatant_id` (introduced in v2.67.3).
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("combatant_id") == bandit_cid
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, (
        f"expected economy_update with combatant_id={bandit_cid}; "
        f"buffered: "
        f"{[(m.get('data') or {}) for m in gm_ws.buffered('economy_update')]}"
    )
    assert econ[-1]["data"]["used"] is True

    # resolved broadcast confirms the prompt cleared.
    assert any(
        (m.get("data") or {}).get("prompt_id") == prompt_id
        for m in _resolved_broadcasts(gm_ws)
    ), "expected reaction_prompt_resolved for the NPC OA prompt"
