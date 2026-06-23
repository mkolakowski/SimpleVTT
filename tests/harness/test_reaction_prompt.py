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


async def _set_auto_apply(gm_client, on: bool) -> None:
    """Toggle the campaign's `auto_apply_damage` so attack hits
    actually deal HP damage (the precondition for damage-restore /
    damage-taken reactions). The demo default is on, but a shared
    dev container may have it flipped off by a prior test."""
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
        f"/campaign/{CAMPAIGN_ID}/settings",
        data=form, follow_redirects=False,
    )


def _prompt_broadcasts(gm_ws) -> list:
    return list(gm_ws.buffered("reaction_prompt"))


def _resolved_broadcasts(gm_ws) -> list:
    return list(gm_ws.buffered("reaction_prompt_resolved"))


def _oa_keys(options) -> list:
    """v2.118.1 — every key that resolves an opportunity attack. The
    v2.99.56+ attack picker yields one ``take-the-oa:{idx}`` key per
    melee weapon/action and only falls back to the bare ``take-the-oa``
    when the watcher has no pickable attacks. These OA tests predate
    the picker and hardcoded the bare key; derive the real key(s) from
    the prompt instead so they pass whether the watcher pickers or
    falls back."""
    return [
        (o.get("key") or "")
        for o in (options or [])
        if (o.get("key") or "") == "take-the-oa"
        or (o.get("key") or "").startswith("take-the-oa:")
    ]


def _first_oa_key(options) -> str:
    keys = _oa_keys(options)
    assert keys, f"expected an OA option (take-the-oa[:idx]); got {options}"
    return keys[0]


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
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
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
    assert _oa_keys(data.get("options")), (
        f"expected a take-the-oa[:idx] option; got options={data.get('options')}"
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
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == tavik["id"]
    ]
    assert prompts
    prompt_id = prompts[0]["data"]["prompt_id"]
    oa_key = _first_oa_key(prompts[0]["data"].get("options"))

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": oa_key,
            "watcher_char_id": tavik["id"],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["reaction_key"] == oa_key
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
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == tavik["id"]
    ]
    prompt_id = prompts[0]["data"]["prompt_id"]
    oa_key = _first_oa_key(prompts[0]["data"].get("options"))

    first = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": oa_key,
            "watcher_char_id": tavik["id"],
        },
    )
    assert first.status_code == 200

    second = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": oa_key,
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
        # v2.79.0 — restore auto_apply_damage to the demo's default
        # (ON, per app/demo_seed.py). Earlier versions of this test
        # restored to OFF (deleted the form key), which polluted the
        # demo campaign state for every subsequent test in the suite
        # and forced v2.71.0+ damage-dependent tests (HR / NPC Parry)
        # to do their own auto-apply toggle dance. The fix is to
        # restore the demo's seeded default value, not the absence
        # of the key.
        form["auto_apply_damage"] = "on"
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


# ── v2.69.0 — Phase 3a: Shield spell prompt + cast ──


async def test_shield_prompt_fires_on_pc_hit(
    gm_client, gm_ws, roster,
):
    """v2.69.0 — when a PC who has Shield in their spell list +
    a 1st+ slot + a free reaction is HIT by an attack, the v2.67.x
    prompt pipeline emits a `reaction_prompt(attack_targeted)` with
    a `cast-shield` option. Krieger swings on Thalindra (Wizard 5
    with Shield as a reaction spell).
    """
    krieger = roster["Krieger Stonefist"]
    thalindra = roster["Thalindra Moonwhisper"]
    # Long rest so Thalindra's slots are full.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )

    thal_cid = f"tok_shield_{thalindra['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": thal_cid,
            "char_id": thalindra["id"],
            "name": thalindra["name"],
            "initiative": 10,
            "hp_current": 32, "hp_max": 32,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Probe until Krieger lands a hit on Thalindra.
    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": thal_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, (
        f"expected reaction_prompt(attack_targeted) for Thalindra; "
        f"buffered prompts: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    keys = [o.get("key") for o in prompts[0]["data"].get("options", [])]
    assert "cast-shield" in keys, (
        f"expected cast-shield option; got {keys}"
    )


async def test_cast_shield_consumes_slot_and_installs_buff(
    gm_client, gm_ws, roster,
):
    """End-to-end: hit Thalindra → prompt fires → POST /use_reaction
    with cast-shield → 1st-level slot used count increments + shield-
    active buff installed + reaction slot flips.
    """
    krieger = roster["Krieger Stonefist"]
    thalindra = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )

    thal_cid = f"tok_shield_cast_{thalindra['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": thal_cid,
            "char_id": thalindra["id"],
            "name": thalindra["name"],
            "initiative": 10,
            "hp_current": 32, "hp_max": 32,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Probe until a hit lands.
    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": thal_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, "expected attack_targeted prompt"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "cast-shield",
            "watcher_char_id": thalindra["id"],
        },
    )
    assert cast.status_code == 200, cast.text

    await asyncio.sleep(0.2)
    # economy_update fires Thalindra's reaction = used.
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Thalindra's reaction"
    assert econ[-1]["data"]["used"] is True

    # spell_slot_update broadcasts the consumed slot.
    slot_msgs = [
        m for m in gm_ws.buffered("spell_slot_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
        and int((m.get("data") or {}).get("level") or 0) >= 1
    ]
    assert slot_msgs, (
        f"expected spell_slot_update for Thalindra's 1st+ slot; "
        f"buffered: {[m.get('data') for m in gm_ws.buffered('spell_slot_update')]}"
    )

    # feature_used card with source=shield-cast.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "shield-cast"
        and (m.get("data") or {}).get("character_id") == thalindra["id"]
    ]
    assert fu, "expected feature_used(source=shield-cast) broadcast"

    # buff_update broadcasts the shield-active install.
    buffs = [
        m for m in gm_ws.buffered("buff_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
    ]
    saw_shield = any(
        any(
            isinstance(b, dict) and b.get("key") == "shield-active"
            for b in (m.get("data") or {}).get("buffs", []) or []
        )
        for m in buffs
    )
    assert saw_shield, (
        f"expected shield-active buff installed for Thalindra; "
        f"buff_update payloads: {[m.get('data') for m in buffs]}"
    )


# ── v2.600.0 — Shield auto-negation of the triggering hit ──


async def test_cast_shield_auto_negates_in_band_hit(
    gm_client, gm_ws, roster,
):
    """v2.600.0 — when the +5 AC from Shield turns the triggering
    hit into a miss (target_ac <= attack_total < target_ac + 5, and
    not a crit), casting Shield via the prompt retroactively restores
    the full applied damage. Reuses the v2.80.0 Uncanny Dodge
    heal-back recipe. Krieger swings on Thalindra until a hit lands
    in the negation band, then Thalindra casts Shield and her HP is
    healed back by exactly the applied damage.
    """
    krieger = roster["Krieger Stonefist"]
    thalindra = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    # Auto-apply ON so the hit actually deals damage (damage_applied
    # > 0 is the precondition for the negation heal-back).
    await _set_auto_apply(gm_client, True)

    thal_cid = f"tok_shield_negate_{thalindra['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": thal_cid,
            "char_id": thalindra["id"],
            "name": thalindra["name"],
            "initiative": 10,
            "hp_current": 32, "hp_max": 32,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Probe until Krieger lands a hit in the Shield negation band:
    # the d20 total beats AC (a hit) but would miss AC+5, and it's
    # not a crit (RAW: a nat-20 always hits regardless of AC).
    in_band = None
    for _ in range(60):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": thal_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        d = resp.json()
        atk_total = d.get("attack_total")
        target_ac = d.get("target_ac")
        if (
            d.get("hit")
            and not d.get("is_crit")
            and int(d.get("damage_applied") or 0) > 0
            and isinstance(atk_total, int)
            and isinstance(target_ac, int)
            and atk_total < target_ac + 5
        ):
            in_band = d
            break
        # Heal Thalindra back to full between probes so each swing
        # starts from the same HP and we don't drop her to 0.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
            json={"type": "long"},
        )
    assert in_band is not None, (
        "no in-band (negatable, non-crit) hit landed in 60 swings"
    )
    dmg = int(in_band["damage_applied"])

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, "expected attack_targeted prompt for Thalindra"
    prompt_id = prompts[-1]["data"]["prompt_id"]

    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "cast-shield",
            "watcher_char_id": thalindra["id"],
        },
    )
    assert cast.status_code == 200, cast.text
    await asyncio.sleep(0.2)

    # feature_used(source=shield-negate) announces the negation.
    neg = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "shield-negate"
        and (m.get("data") or {}).get("character_id") == thalindra["id"]
    ]
    assert neg, (
        f"expected feature_used(source=shield-negate); "
        f"got sources "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )
    assert int(neg[-1]["data"].get("heal_back") or 0) == dmg

    # character_hp_update restores exactly the applied damage.
    hp_up = [
        m for m in gm_ws.buffered("character_hp_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
        and (m.get("data") or {}).get("source") == "shield-negate"
    ]
    assert hp_up, "expected character_hp_update(source=shield-negate)"
    assert int(hp_up[-1]["data"].get("delta") or 0) == dmg


# ── v2.70.0 — Phase 3b: Counterspell prompt + cast ──


async def test_counterspell_prompt_fires_on_pc_cast(
    gm_client, gm_ws, roster,
):
    """v2.70.0 — when a PC casts a leveled spell within 60 ft of a
    watcher who has Counterspell prepared + a 3rd+ slot + a free
    reaction, the new `spell_cast_near` trigger fires. Lyra casts
    Suggestion (L2) targeted at Krieger; Thalindra (Wizard with
    Counterspell + L3 slot) is positioned 5 ft away from Lyra so
    the 60 ft range check passes.
    """
    lyra = roster["Lyra Sunstrider"]
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    # Long-rest both casters so slots are fresh.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    # Place tokens within 60 ft of each other (one cell apart).
    await _place_token(gm_client, lyra["id"], 300.0, 300.0)
    await _place_token(gm_client, thalindra["id"], 370.0, 300.0)
    await _place_token(gm_client, krieger["id"], 440.0, 300.0)

    thal_cid = f"tok_cs_{thalindra['id']}"
    krieg_cid = f"tok_cs_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=14, hp=40),
        {
            "id": thal_cid,
            "char_id": thalindra["id"],
            "name": thalindra["name"],
            "initiative": 10,
            "hp_current": 32, "hp_max": 32,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
        {
            "id": krieg_cid,
            "char_id": krieger["id"],
            "name": krieger["name"],
            "initiative": 8,
            "hp_current": 75, "hp_max": 75,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Lyra Suggestion is index 9 in the demo Bard sheet (see
    # test_use_countercharm SUGGESTION_INDEX = 9).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": 9,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": krieg_cid,
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "spell_cast_near"
    ]
    assert prompts, (
        f"expected reaction_prompt(spell_cast_near) for Thalindra; "
        f"buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    options = prompts[0]["data"].get("options", []) or []
    keys = [o.get("key") for o in options]
    assert "cast-counterspell" in keys, (
        f"expected cast-counterspell option; got {keys}"
    )
    # Params carry the slot level (3, lowest available) + spell name.
    cs_option = next(
        (o for o in options if o.get("key") == "cast-counterspell"), {}
    )
    params = cs_option.get("params") or {}
    assert int(params.get("slot_level") or 0) == 3
    assert (params.get("spell_name") or "").lower() == "suggestion"
    assert int(params.get("incoming_spell_level") or 0) == 2


async def test_cast_counterspell_consumes_slot(
    gm_client, gm_ws, roster,
):
    """End-to-end: Lyra casts Suggestion → Thalindra prompt fires →
    POST /use_reaction with cast-counterspell → Thalindra's L3 slot
    used count increments + reaction slot flips + feature_used
    (source=counterspell-cast) fires.
    """
    lyra = roster["Lyra Sunstrider"]
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    await _place_token(gm_client, lyra["id"], 300.0, 300.0)
    await _place_token(gm_client, thalindra["id"], 370.0, 300.0)
    await _place_token(gm_client, krieger["id"], 440.0, 300.0)

    thal_cid = f"tok_cs2_{thalindra['id']}"
    krieg_cid = f"tok_cs2_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=14, hp=40),
        {
            "id": thal_cid,
            "char_id": thalindra["id"],
            "name": thalindra["name"],
            "initiative": 10,
            "hp_current": 32, "hp_max": 32,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
        {
            "id": krieg_cid,
            "char_id": krieger["id"],
            "name": krieger["name"],
            "initiative": 8,
            "hp_current": 75, "hp_max": 75,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": 9,
            "slot_level": 2,
            "class_slug": "bard",
            "target_combatant_id": krieg_cid,
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "spell_cast_near"
    ]
    assert prompts, "expected spell_cast_near prompt for Thalindra"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "cast-counterspell",
            "watcher_char_id": thalindra["id"],
        },
    )
    assert cast.status_code == 200, cast.text

    await asyncio.sleep(0.2)
    # economy_update: Thalindra's reaction flips True.
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Thalindra's reaction"
    assert econ[-1]["data"]["used"] is True

    # spell_slot_update: L3 wizard slot decremented.
    slot_msgs = [
        m for m in gm_ws.buffered("spell_slot_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
        and int((m.get("data") or {}).get("level") or 0) == 3
    ]
    assert slot_msgs, (
        f"expected spell_slot_update L3 for Thalindra; "
        f"buffered: {[m.get('data') for m in gm_ws.buffered('spell_slot_update')]}"
    )

    # feature_used card with source=counterspell-cast names Lyra +
    # Suggestion + L3 slot.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "counterspell-cast"
        and (m.get("data") or {}).get("character_id") == thalindra["id"]
    ]
    assert fu, "expected feature_used(source=counterspell-cast) broadcast"
    last = fu[-1]["data"]
    # Outcome hint = "auto" since L3 slot ≥ L2 incoming.
    assert last.get("outcome_hint") == "auto"
    assert last.get("slot_level") == 3
    assert (last.get("countered_spell_name") or "").lower() == "suggestion"


# ── v2.71.0 — Phase 3c: Hellish Rebuke + Absorb Elements ──


async def test_hellish_rebuke_prompt_fires_on_pc_damage(
    gm_client, gm_ws, roster,
):
    """v2.71.0 — when a Warlock with Hellish Rebuke prepared + a slot
    available + reaction unused takes damage, `damage_taken` fires
    with a `cast-hellish-rebuke` option. Magnus (Warlock 5, Pact
    Magic L3 x2) is the demo Warlock — Krieger swings on him until
    a hit lands.
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    # v2.79.0 — demo default for auto_apply_damage is True (seeded in
    # app/demo_seed.py); the v2.67.2 UD test restoration was fixed to
    # preserve that default. No toggle dance needed here anymore.

    magnus_cid = f"tok_hr_{magnus['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": magnus_cid,
            "char_id": magnus["id"],
            "name": magnus["name"],
            "initiative": 10,
            "hp_current": 50, "hp_max": 50,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Krieger swings until a hit lands.
    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": magnus_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == magnus["id"]
        and (m.get("data") or {}).get("trigger_event") == "damage_taken"
    ]
    assert prompts, (
        f"expected reaction_prompt(damage_taken) for Magnus; "
        f"buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    keys = [o.get("key") for o in prompts[0]["data"].get("options", [])]
    assert "cast-hellish-rebuke" in keys, (
        f"expected cast-hellish-rebuke option; got {keys}"
    )


async def test_cast_hellish_rebuke_consumes_slot(
    gm_client, gm_ws, roster,
):
    """End-to-end: Krieger hits Magnus → prompt fires → POST
    /use_reaction with cast-hellish-rebuke → Magnus's Pact slot used
    count increments + reaction flips + feature_used(source=
    hellish-rebuke-cast) fires.
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )

    magnus_cid = f"tok_hr2_{magnus['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": magnus_cid,
            "char_id": magnus["id"],
            "name": magnus["name"],
            "initiative": 10,
            "hp_current": 50, "hp_max": 50,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": magnus_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == magnus["id"]
        and (m.get("data") or {}).get("trigger_event") == "damage_taken"
    ]
    assert prompts, "expected damage_taken prompt for Magnus"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "cast-hellish-rebuke",
            "watcher_char_id": magnus["id"],
        },
    )
    assert cast.status_code == 200, cast.text

    await asyncio.sleep(0.2)
    # economy_update: reaction flipped.
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == magnus["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Magnus's reaction"
    assert econ[-1]["data"]["used"] is True

    # spell_slot_update: Pact slot decremented (Magnus only has L3
    # slots).
    slot_msgs = [
        m for m in gm_ws.buffered("spell_slot_update")
        if (m.get("data") or {}).get("character_id") == magnus["id"]
        and int((m.get("data") or {}).get("level") or 0) >= 1
    ]
    assert slot_msgs, (
        f"expected spell_slot_update for Magnus's slot; buffered: "
        f"{[m.get('data') for m in gm_ws.buffered('spell_slot_update')]}"
    )

    # feature_used(source=hellish-rebuke-cast) fires.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "hellish-rebuke-cast"
        and (m.get("data") or {}).get("character_id") == magnus["id"]
    ]
    assert fu, "expected feature_used(source=hellish-rebuke-cast)"
    last = fu[-1]["data"]
    assert last.get("damage_type") == "fire"
    # Magnus's slot is L3 → damage_dice = 1 + 3 = 4 → "4d10".
    assert last.get("damage_expr") == "4d10"


# ── v2.118.0 — Phase 7: Protective Field (Psi Warrior) on damage ──


async def _patch_sheet_pf(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def garrik_psi_warrior(gm_client, roster):
    """Garrik (Fighter) patched into the Psi Warrior archetype so the
    damage_taken prompt surfaces Protective Field. Restore-safe
    (v2.117.x discipline): snapshots his original subclass + level via
    the sheet-json endpoint and restores them in teardown — never the
    old `{"subclass": "Champion", "resources": []}` hardcoded reset
    that wiped his Lucky points for downstream tests."""
    garrik = roster["Garrik Ironside"]
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-json",
    )
    orig = (snap.json() or {}).get("sheet") or {}
    orig_subclass = orig.get("subclass")
    orig_level = orig.get("level")
    await _patch_sheet_pf(
        gm_client, garrik["id"],
        {"subclass": "Psi Warrior", "level": 9},
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        restore = {}
        if orig_subclass is not None:
            restore["subclass"] = orig_subclass
        if orig_level is not None:
            restore["level"] = orig_level
        if restore:
            await _patch_sheet_pf(
                gm_client, garrik["id"], restore, class_slug="fighter",
            )


async def test_protective_field_prompt_fires_on_pc_damage(
    gm_client, gm_ws, garrik_psi_warrior, roster,
):
    """v2.118.0 — a Psi Warrior who takes damage with a free reaction
    gets a `damage_taken` prompt carrying a `use-protective-field`
    option (reduce the damage by a Psionic Energy die + INT mod).
    Krieger swings on Garrik (patched Psi Warrior) until a hit lands.
    """
    garrik = garrik_psi_warrior
    krieger = roster["Krieger Stonefist"]
    # Long rest so Garrik starts at full HP (leaves room to heal back).
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )

    garrik_cid = f"tok_pf_{garrik['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": garrik_cid,
            "char_id": garrik["id"],
            "name": garrik["name"],
            "initiative": 10,
            "hp_current": 80, "hp_max": 80,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": garrik_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == garrik["id"]
        and (m.get("data") or {}).get("trigger_event") == "damage_taken"
    ]
    assert prompts, (
        f"expected reaction_prompt(damage_taken) for Garrik; buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    options = prompts[0]["data"].get("options", []) or []
    keys = [o.get("key") for o in options]
    assert "use-protective-field" in keys, (
        f"expected use-protective-field option; got {keys}"
    )
    pf_opt = next(
        (o for o in options if o.get("key") == "use-protective-field"), {}
    )
    params = pf_opt.get("params") or {}
    # Garrik Lv 9 Psi Warrior → d8 Psionic Energy die.
    assert int(params.get("die_size") or 0) == 8
    assert params.get("target_combatant_id") == garrik_cid


async def test_use_protective_field_reduces_damage(
    gm_client, gm_ws, garrik_psi_warrior, roster,
):
    """End-to-end: Krieger hits Garrik (Psi Warrior) → prompt fires →
    POST /use_reaction with use-protective-field → reaction flips +
    feature_used(source=protective-field) names the reduction + the
    damaged combatant heals back by that much.
    """
    garrik = garrik_psi_warrior
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )

    garrik_cid = f"tok_pf2_{garrik['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": garrik_cid,
            "char_id": garrik["id"],
            "name": garrik["name"],
            "initiative": 10,
            "hp_current": 80, "hp_max": 80,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": garrik_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == garrik["id"]
        and (m.get("data") or {}).get("trigger_event") == "damage_taken"
    ]
    assert prompts, "expected damage_taken prompt for Garrik"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "use-protective-field",
            "watcher_char_id": garrik["id"],
        },
    )
    assert use.status_code == 200, use.text

    await asyncio.sleep(0.2)
    # economy_update: Garrik's reaction flips to used.
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == garrik["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Garrik's reaction"
    assert econ[-1]["data"]["used"] is True

    # feature_used(source=protective-field) names the reduction.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "protective-field"
        and (m.get("data") or {}).get("character_id") == garrik["id"]
    ]
    assert fu, "expected feature_used(source=protective-field)"
    last = fu[-1]["data"]
    assert int(last.get("reduction") or 0) >= 1
    # 1d8 + INT mod, min 1.
    assert last.get("psionic_die") == "1d8"
    # The damaged combatant healed back by the reduction (Garrik was
    # below max after the hit, so at least 1 HP is restored).
    assert int(last.get("applied") or 0) >= 1


# ── v2.121.0 — Phase 7: Protective Field ALLY case (within 30 ft) ──


async def test_protective_field_ally_prompt_fires_for_nearby_psi_warrior(
    gm_client, gm_ws, garrik_psi_warrior, roster,
):
    """v2.121.0 — when a creature takes damage within 30 ft of a Psi
    Warrior, the Psi Warrior gets an `ally_damaged_near` prompt to
    shield it (the RAW "or another creature within 30 ft" half).
    Garrik (patched Psi Warrior) is placed one cell from Tavik; Krieger
    hits Tavik until damage lands → Garrik gets the ally prompt whose
    target is Tavik's combatant.
    """
    garrik = garrik_psi_warrior
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]

    # Place Garrik one cell (≈5 ft) from Tavik, Krieger adjacent.
    await _place_token(gm_client, garrik["id"], 300.0, 300.0)
    await _place_token(gm_client, tavik["id"], 370.0, 300.0)
    await _place_token(gm_client, krieger["id"], 440.0, 300.0)

    tavik_cid = f"tok_pfa_{tavik['id']}"
    krieg_cid = f"tok_pfa_kr_{krieger['id']}"
    garrik_cid = f"tok_pfa_g_{garrik['id']}"
    await _seed_battle(gm_client, [
        {
            "id": krieg_cid, "char_id": krieger["id"],
            "name": krieger["name"], "initiative": 14,
            "hp_current": 75, "hp_max": 75, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
        {
            "id": tavik_cid, "char_id": tavik["id"],
            "name": tavik["name"], "initiative": 10,
            "hp_current": 40, "hp_max": 40, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
        {
            "id": garrik_cid, "char_id": garrik["id"],
            "name": garrik["name"], "initiative": 8,
            "hp_current": 80, "hp_max": 80, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": tavik_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == garrik["id"]
        and (m.get("data") or {}).get("trigger_event") == "ally_damaged_near"
    ]
    assert prompts, (
        f"expected reaction_prompt(ally_damaged_near) for Garrik; buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    options = prompts[0]["data"].get("options", []) or []
    keys = [o.get("key") for o in options]
    assert "use-protective-field" in keys, (
        f"expected use-protective-field option; got {keys}"
    )
    pf_opt = next(o for o in options if o.get("key") == "use-protective-field")
    params = pf_opt.get("params") or {}
    # The protect target is the DAMAGED ALLY (Tavik), not Garrik.
    assert params.get("target_combatant_id") == tavik_cid
    assert int(params.get("die_size") or 0) == 8


async def test_use_protective_field_heals_damaged_ally(
    gm_client, gm_ws, garrik_psi_warrior, roster,
):
    """End-to-end: Krieger hits Tavik near Garrik (Psi Warrior) → ally
    prompt fires → POST /use_reaction with use-protective-field →
    Garrik's reaction flips + Tavik (the ally) heals back the reduction
    via feature_used(source=protective-field, applied>=1).
    """
    garrik = garrik_psi_warrior
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    # Long rest Tavik so he's at full HP (room to heal back).
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )

    await _place_token(gm_client, garrik["id"], 300.0, 300.0)
    await _place_token(gm_client, tavik["id"], 370.0, 300.0)
    await _place_token(gm_client, krieger["id"], 440.0, 300.0)

    tavik_cid = f"tok_pfa2_{tavik['id']}"
    krieg_cid = f"tok_pfa2_kr_{krieger['id']}"
    garrik_cid = f"tok_pfa2_g_{garrik['id']}"
    await _seed_battle(gm_client, [
        {
            "id": krieg_cid, "char_id": krieger["id"],
            "name": krieger["name"], "initiative": 14,
            "hp_current": 75, "hp_max": 75, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
        {
            "id": tavik_cid, "char_id": tavik["id"],
            "name": tavik["name"], "initiative": 10,
            "hp_current": 40, "hp_max": 40, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
        {
            "id": garrik_cid, "char_id": garrik["id"],
            "name": garrik["name"], "initiative": 8,
            "hp_current": 80, "hp_max": 80, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": tavik_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == garrik["id"]
        and (m.get("data") or {}).get("trigger_event") == "ally_damaged_near"
    ]
    assert prompts, "expected ally_damaged_near prompt for Garrik"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "use-protective-field",
            "watcher_char_id": garrik["id"],
        },
    )
    assert use.status_code == 200, use.text

    await asyncio.sleep(0.2)
    # Garrik's reaction flips.
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == garrik["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Garrik's reaction"
    assert econ[-1]["data"]["used"] is True

    # feature_used(source=protective-field) — Garrik shields, Tavik heals.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "protective-field"
        and (m.get("data") or {}).get("character_id") == garrik["id"]
    ]
    assert fu, "expected feature_used(source=protective-field)"
    last = fu[-1]["data"]
    assert int(last.get("reduction") or 0) >= 1
    assert int(last.get("applied") or 0) >= 1


# ── v2.119.0 — Phase 7: Riposte (Battle Master) on a missed attack ──


@pytest_asyncio.fixture
async def garrik_riposte_bm(gm_client, roster):
    """Garrik patched into Battle Master (Lv 9) with a full Superiority
    Dice pool so a missed attack offers Riposte. Restore-safe: snapshots
    subclass + level + resources via sheet-json and restores in finally
    (no hardcoded `{"subclass": "Champion", "resources": []}` reset)."""
    garrik = roster["Garrik Ironside"]
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-json",
    )
    orig = (snap.json() or {}).get("sheet") or {}
    orig_subclass = orig.get("subclass")
    orig_level = orig.get("level")
    orig_resources = orig.get("resources") or []
    await _patch_sheet_pf(
        gm_client, garrik["id"],
        {
            "subclass": "Battle Master",
            "level": 9,
            "superiority_die_size": "d8",
            "resources": [{
                "key": "superiority-dice", "name": "Superiority Dice",
                "current": 4, "max": 4, "reset": "short",
                "source": "fighter Lv 3 / Combat Superiority",
                "class_slug": "fighter", "manual": False,
            }],
        },
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        restore = {"resources": orig_resources}
        if orig_subclass is not None:
            restore["subclass"] = orig_subclass
        if orig_level is not None:
            restore["level"] = orig_level
        await _patch_sheet_pf(
            gm_client, garrik["id"], restore, class_slug="fighter",
        )


async def test_riposte_prompt_fires_on_missed_attack(
    gm_client, gm_ws, garrik_riposte_bm, roster,
):
    """v2.119.0 — when a PC attack MISSES a Battle Master who has a free
    reaction + a Superiority Die, a `reaction_prompt(attack_missed)`
    fires with a `use-riposte:{idx}` option. Krieger swings on Garrik
    (patched Battle Master) until a MISS lands.
    """
    garrik = garrik_riposte_bm
    krieger = roster["Krieger Stonefist"]

    garrik_cid = f"tok_ri_{garrik['id']}"
    krieger_cid = f"tok_ri_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        {
            "id": krieger_cid, "char_id": krieger["id"],
            "name": krieger["name"], "initiative": 12,
            "hp_current": 75, "hp_max": 75, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
        {
            "id": garrik_cid, "char_id": garrik["id"],
            "name": garrik["name"], "initiative": 10,
            "hp_current": 80, "hp_max": 80, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(30):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": garrik_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit") is False:
            break
    else:
        raise AssertionError("no miss landed in 30 swings")

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == garrik["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_missed"
    ]
    assert prompts, (
        f"expected reaction_prompt(attack_missed) for Garrik; buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    options = prompts[0]["data"].get("options", []) or []
    ri_keys = [
        o.get("key") for o in options
        if (o.get("key") or "").startswith("use-riposte:")
    ]
    assert ri_keys, f"expected a use-riposte:{{idx}} option; got {[o.get('key') for o in options]}"
    ri_opt = next(o for o in options if o.get("key") == ri_keys[0])
    params = ri_opt.get("params") or {}
    assert params.get("target_combatant_id") == krieger_cid
    assert params.get("die_size") == "d8"


async def test_use_riposte_resolves_counter_attack(
    gm_client, gm_ws, garrik_riposte_bm, roster,
):
    """End-to-end: Krieger misses Garrik (Battle Master) → prompt fires
    → POST /use_reaction with the use-riposte:{idx} key → reaction flips
    + a Superiority Die is spent (resource_update 4 → 3) +
    feature_used(source=riposte) names the counter-attack.
    """
    garrik = garrik_riposte_bm
    krieger = roster["Krieger Stonefist"]

    garrik_cid = f"tok_ri2_{garrik['id']}"
    krieger_cid = f"tok_ri2_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        {
            "id": krieger_cid, "char_id": krieger["id"],
            "name": krieger["name"], "initiative": 12,
            "hp_current": 75, "hp_max": 75, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
        {
            "id": garrik_cid, "char_id": garrik["id"],
            "name": garrik["name"], "initiative": 10,
            "hp_current": 80, "hp_max": 80, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(30):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": garrik_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit") is False:
            break
    else:
        raise AssertionError("no miss landed in 30 swings")
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == garrik["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_missed"
    ]
    assert prompts, "expected attack_missed prompt for Garrik"
    prompt = prompts[0]["data"]
    prompt_id = prompt["prompt_id"]
    ri_key = next(
        o["key"] for o in prompt["options"]
        if (o.get("key") or "").startswith("use-riposte:")
    )

    gm_ws.mark()
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": ri_key,
            "watcher_char_id": garrik["id"],
        },
    )
    assert use.status_code == 200, use.text

    await asyncio.sleep(0.2)
    # economy_update: Garrik's reaction flips to used.
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == garrik["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Garrik's reaction"
    assert econ[-1]["data"]["used"] is True

    # resource_update: a Superiority Die was spent (4 → 3).
    sd = [
        m for m in gm_ws.buffered("resource_update")
        if (m.get("data") or {}).get("character_id") == garrik["id"]
        and (m.get("data") or {}).get("key") == "superiority-dice"
    ]
    assert sd, "expected resource_update for superiority-dice"
    assert sd[-1]["data"]["current"] == 3

    # feature_used(source=riposte) names the counter-attack.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "riposte"
        and (m.get("data") or {}).get("character_id") == garrik["id"]
    ]
    assert fu, "expected feature_used(source=riposte)"
    last = fu[-1]["data"]
    assert last.get("attacked") is True
    assert int(last.get("extra_damage_on_hit") or 0) >= 1
    assert last.get("dice_remaining") == 3


# ── v2.120.0 — Phase 7: Chronal Shift (Chronurgy Wizard) on a save ──


@pytest_asyncio.fixture
async def thalindra_chronurgy(gm_client, roster):
    """Thalindra (Wizard) patched into the Chronurgy Magic subclass +
    a full Chronal Shift use pool so a resolved save offers the reroll.
    Restore-safe: snapshots subclass + resources via sheet-json and
    restores in finally."""
    thalindra = roster["Thalindra Moonwhisper"]
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-json",
    )
    orig = (snap.json() or {}).get("sheet") or {}
    orig_subclass = orig.get("subclass")
    orig_resources = orig.get("resources") or []
    await _patch_sheet_pf(
        gm_client, thalindra["id"],
        {
            "subclass": "Chronurgy Magic",
            "resources": [{
                "key": "chronal-shift", "label": "Chronal Shift",
                "current": 2, "max": 2, "reset": "long",
            }],
        },
        class_slug="wizard",
    )
    try:
        yield thalindra
    finally:
        restore = {"resources": orig_resources}
        if orig_subclass is not None:
            restore["subclass"] = orig_subclass
        await _patch_sheet_pf(
            gm_client, thalindra["id"], restore, class_slug="wizard",
        )


async def test_chronal_shift_prompt_fires_on_failed_save(
    gm_client, gm_ws, thalindra_chronurgy, roster,
):
    """v2.120.0 — Chronal Shift works on ANY save outcome (unlike
    passed-gated Silvery Barbs). Krieger FAILS a DC 30 save → a
    `save_resolved` prompt fires for Thalindra (Chronurgy Wizard) with
    a `use-chronal-shift` option but NO `cast-silvery-barbs` option
    (the save failed, so SB is ineligible).
    """
    thalindra = thalindra_chronurgy
    krieger = roster["Krieger Stonefist"]

    thal_cid = f"tok_cs_{thalindra['id']}"
    krieg_cid = f"tok_cs_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        {
            "id": krieg_cid, "char_id": krieger["id"],
            "name": krieger["name"], "initiative": 12,
            "hp_current": 75, "hp_max": 75, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
        {
            "id": thal_cid, "char_id": thalindra["id"],
            "name": thalindra["name"], "initiative": 10,
            "hp_current": 32, "hp_max": 32, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # DC 30 STR save — Krieger (Barbarian +7) cannot reach it, so the
    # save fails (Silvery Barbs would be ineligible; Chronal Shift still
    # applies).
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request",
        json={
            "label": "STR save", "base_expression": "1d20",
            "stat_key": "str_save", "dc": 30, "visibility": "public",
        },
    )
    assert rr.status_code == 200, rr.text
    req_id = rr.json()["id"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request/{req_id}/respond",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "save_resolved"
    ]
    assert prompts, (
        f"expected reaction_prompt(save_resolved) for Thalindra; buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    options = prompts[0]["data"].get("options", []) or []
    keys = [o.get("key") for o in options]
    assert "use-chronal-shift" in keys, (
        f"expected use-chronal-shift option on a failed save; got {keys}"
    )
    assert "cast-silvery-barbs" not in keys, (
        f"Silvery Barbs is passed-gated and must not appear on a failed "
        f"save; got {keys}"
    )
    cs_opt = next(o for o in options if o.get("key") == "use-chronal-shift")
    params = cs_opt.get("params") or {}
    assert params.get("target_combatant_id") == krieg_cid
    assert int(params.get("uses_before") or 0) == 2


async def test_use_chronal_shift_decrements_uses(
    gm_client, gm_ws, thalindra_chronurgy, roster,
):
    """End-to-end: Krieger fails a save → prompt fires → POST
    /use_reaction with use-chronal-shift → reaction flips + a Chronal
    Shift use is spent (resource_update 2 → 1) + feature_used(source=
    chronal-shift) names the forced reroll.
    """
    thalindra = thalindra_chronurgy
    krieger = roster["Krieger Stonefist"]

    thal_cid = f"tok_cs2_{thalindra['id']}"
    krieg_cid = f"tok_cs2_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        {
            "id": krieg_cid, "char_id": krieger["id"],
            "name": krieger["name"], "initiative": 12,
            "hp_current": 75, "hp_max": 75, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
        {
            "id": thal_cid, "char_id": thalindra["id"],
            "name": thalindra["name"], "initiative": 10,
            "hp_current": 32, "hp_max": 32, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request",
        json={
            "label": "STR save", "base_expression": "1d20",
            "stat_key": "str_save", "dc": 30, "visibility": "public",
        },
    )
    assert rr.status_code == 200, rr.text
    req_id = rr.json()["id"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request/{req_id}/respond",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 200, resp.text
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "save_resolved"
    ]
    assert prompts, "expected save_resolved prompt for Thalindra"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "use-chronal-shift",
            "watcher_char_id": thalindra["id"],
        },
    )
    assert use.status_code == 200, use.text

    await asyncio.sleep(0.2)
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Thalindra's reaction"
    assert econ[-1]["data"]["used"] is True

    rsc = [
        m for m in gm_ws.buffered("resource_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
        and (m.get("data") or {}).get("key") == "chronal-shift"
    ]
    assert rsc, "expected resource_update for chronal-shift"
    assert rsc[-1]["data"]["current"] == 1

    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "chronal-shift"
        and (m.get("data") or {}).get("character_id") == thalindra["id"]
    ]
    assert fu, "expected feature_used(source=chronal-shift)"
    assert fu[-1]["data"].get("uses_remaining") == 1


# ── v2.80.0 — Uncanny Dodge vs Defensive Duelist interaction ──


async def test_uncanny_dodge_suppressed_when_dd_eligible(
    gm_client, gm_ws, roster,
):
    """v2.80.0 — UD's v2.49.243 auto-fire path now suppresses itself
    when the watcher PC has other attack_targeted reactions eligible
    (DD / Shield / Lucky / item-reactions). Closes the Pip-vs-DD
    interaction footgun filed in v2.74.0: previously, UD silently
    consumed the reaction before the player could pick DD.

    Test pattern: PATCH Defensive Duelist onto Pip's feats list,
    swing on Pip until a hit lands, assert NO auto-halve (damage
    applies at full) AND the attack_targeted prompt surfaces BOTH
    cast-uncanny-dodge AND use-defensive-duelist. Restore Pip's
    feats in finally.
    """
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]

    # PATCH Pip with the Defensive Duelist feat. _SHEET_PATCH_KEYS
    # allowlist (v2.68.11) lets the harness mutate sheet.feats.
    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"feats": [
            {"slug": "defensive-duelist", "name": "Defensive Duelist"},
        ]},
    )
    assert patch.status_code == 200, patch.text
    try:
        pip_cid = f"tok_ud_dd_{pip['id']}"
        await _seed_battle(gm_client, [
            _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
            {
                "id": pip_cid,
                "char_id": pip["id"],
                "name": pip["name"],
                "initiative": 10,
                "hp_current": 45, "hp_max": 45,
                "buffs": [],
                "economy": {
                    "action": False, "bonus": False,
                    "reaction": False, "movement": 0,
                },
            },
        ])
        await asyncio.sleep(0.15)
        gm_ws.mark()

        for _ in range(20):
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": krieger["id"],
                    "attack_index": 0,
                    "target_combatant_id": pip_cid,
                    "override": True,
                    "override_range": True,
                },
            )
            assert resp.status_code == 200, resp.text
            if resp.json().get("hit"):
                break
        else:
            raise AssertionError("no hit landed in 20 swings")

        await asyncio.sleep(0.2)
        # No feature_used(source=uncanny-dodge) auto-fire broadcast
        # — UD suppressed itself because DD is eligible.
        ud_autofires = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source") == "uncanny-dodge"
        ]
        assert not ud_autofires, (
            f"expected NO uncanny-dodge auto-fire when DD eligible; "
            f"got {ud_autofires}"
        )
        # attack_targeted prompt surfaces both options.
        prompts = [
            m for m in _prompt_broadcasts(gm_ws)
            if (m.get("data") or {}).get("watcher_char_id") == pip["id"]
            and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
        ]
        assert prompts, "expected attack_targeted prompt for Pip"
        keys = [o.get("key") for o in prompts[0]["data"].get("options", [])]
        assert "cast-uncanny-dodge" in keys, (
            f"expected cast-uncanny-dodge option; got {keys}"
        )
        assert "use-defensive-duelist" in keys, (
            f"expected use-defensive-duelist option; got {keys}"
        )
    finally:
        # Restore Pip's empty feats list.
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"feats": []},
        )


async def test_cast_uncanny_dodge_via_prompt_heals_back_half(
    gm_client, gm_ws, roster,
):
    """End-to-end: PATCH DD onto Pip, NPC hits Pip → prompt fires →
    POST /use_reaction with cast-uncanny-dodge → Pip's reaction flips
    + HP heals back ceil(damage/2) + feature_used(source=
    uncanny-dodge) names the halve.
    """
    pip = roster["Pip Quickfingers"]
    krieger = roster["Krieger Stonefist"]

    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"feats": [
            {"slug": "defensive-duelist", "name": "Defensive Duelist"},
        ]},
    )
    assert patch.status_code == 200, patch.text
    try:
        pip_cid = f"tok_ud_dd2_{pip['id']}"
        await _seed_battle(gm_client, [
            _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
            {
                "id": pip_cid,
                "char_id": pip["id"],
                "name": pip["name"],
                "initiative": 10,
                "hp_current": 45, "hp_max": 45,
                "buffs": [],
                "economy": {
                    "action": False, "bonus": False,
                    "reaction": False, "movement": 0,
                },
            },
        ])
        await asyncio.sleep(0.15)
        gm_ws.mark()

        landed = None
        for _ in range(20):
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": krieger["id"],
                    "attack_index": 0,
                    "target_combatant_id": pip_cid,
                    "override": True,
                    "override_range": True,
                },
            )
            assert resp.status_code == 200, resp.text
            if resp.json().get("hit"):
                landed = resp.json()
                break
        else:
            raise AssertionError("no hit landed in 20 swings")
        await asyncio.sleep(0.2)

        prompts = [
            m for m in _prompt_broadcasts(gm_ws)
            if (m.get("data") or {}).get("watcher_char_id") == pip["id"]
            and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
        ]
        assert prompts, "expected attack_targeted prompt"
        prompt_id = prompts[0]["data"]["prompt_id"]
        ud_opt = next(
            (o for o in prompts[0]["data"]["options"]
             if o.get("key") == "cast-uncanny-dodge"), {}
        )
        expected_damage = int((ud_opt.get("params") or {}).get("damage_applied") or 0)
        expected_heal_back = int((ud_opt.get("params") or {}).get("heal_back") or 0)
        assert expected_damage > 0
        assert expected_heal_back > 0

        gm_ws.mark()
        use = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
            json={
                "prompt_id": prompt_id,
                "reaction_key": "cast-uncanny-dodge",
                "watcher_char_id": pip["id"],
            },
        )
        assert use.status_code == 200, use.text

        await asyncio.sleep(0.2)
        econ = [
            m for m in gm_ws.buffered("economy_update")
            if (m.get("data") or {}).get("character_id") == pip["id"]
            and (m.get("data") or {}).get("slot") == "reaction"
        ]
        assert econ, "expected economy_update for Pip's reaction"
        assert econ[-1]["data"]["used"] is True

        # character_hp_update broadcast carries the heal-back delta.
        hp_updates = [
            m for m in gm_ws.buffered("character_hp_update")
            if (m.get("data") or {}).get("character_id") == pip["id"]
            and (m.get("data") or {}).get("source") == "uncanny-dodge"
        ]
        assert hp_updates, "expected character_hp_update from UD cast"
        assert hp_updates[-1]["data"].get("delta") == expected_heal_back

        # feature_used named the halve.
        fu = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source") == "uncanny-dodge"
            and (m.get("data") or {}).get("character_id") == pip["id"]
        ]
        assert fu, "expected feature_used(source=uncanny-dodge)"
        assert fu[-1]["data"].get("damage_applied") == expected_damage
        assert fu[-1]["data"].get("heal_back") == expected_heal_back
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"feats": []},
        )


# ── v2.78.0 — Phase 5: Item reactions ──


async def test_item_reaction_prompt_includes_cloak_of_displacement(
    gm_client, gm_ws, roster,
):
    """v2.78.0 — when a PC with an equipped item carrying a
    `_reactions[]` entry binding to attack_targeted is hit, the
    v2.69.0 prompt surfaces the item-derived option alongside any
    feat-based options. Lyra got Cloak of Displacement in the
    v2.78.0 demo seed.
    """
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]

    lyra_cid = f"tok_item_{lyra['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": lyra_cid,
            "char_id": lyra["id"],
            "name": lyra["name"],
            "initiative": 10,
            "hp_current": 40, "hp_max": 40,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": lyra_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == lyra["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, "expected attack_targeted prompt for Lyra"
    keys = [o.get("key") for o in prompts[0]["data"].get("options", [])]
    # DD option still present (Lyra's other reaction surface from v2.74).
    assert "use-defensive-duelist" in keys
    # Cloak's _reactions entry should now appear too.
    assert "item-cloak-displacement-advantage" in keys, (
        f"expected item-cloak-displacement-advantage option; got {keys}"
    )


async def test_use_item_reaction_marks_reaction(
    gm_client, gm_ws, roster,
):
    """End-to-end: Krieger hits Lyra → prompt fires → POST
    /use_reaction with the Cloak of Displacement item key → Lyra's
    reaction flips + feature_used(source=item-reaction) names the
    item.
    """
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]

    lyra_cid = f"tok_item2_{lyra['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": lyra_cid,
            "char_id": lyra["id"],
            "name": lyra["name"],
            "initiative": 10,
            "hp_current": 40, "hp_max": 40,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": lyra_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == lyra["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, "expected attack_targeted prompt for Lyra"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "item-cloak-displacement-advantage",
            "watcher_char_id": lyra["id"],
        },
    )
    assert use.status_code == 200, use.text

    await asyncio.sleep(0.2)
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == lyra["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Lyra's reaction"
    assert econ[-1]["data"]["used"] is True

    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "item-reaction"
        and (m.get("data") or {}).get("character_id") == lyra["id"]
    ]
    assert fu, "expected feature_used(source=item-reaction)"
    last = fu[-1]["data"]
    assert last.get("item_slug") == "cloak-of-displacement"
    assert (last.get("item_name") or "").lower() == "cloak of displacement"


# ── v2.77.0 — Phase 4b: Lucky feat ──


async def test_lucky_prompt_fires_on_pc_hit(
    gm_client, gm_ws, roster,
):
    """v2.77.0 — when a PC with the Lucky feat (+ remaining charges)
    is hit by an attack, the v2.69.0 attack_targeted prompt now also
    surfaces `use-lucky`. Garrik got the feat in the v2.77.0 demo
    seed; his luck-point resource starts at 3/3.
    """
    garrik = roster["Garrik Ironside"]
    krieger = roster["Krieger Stonefist"]
    # Long-rest Garrik to ensure luck points are at 3/3 even if a
    # prior test decremented them.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )

    garrik_cid = f"tok_lk_{garrik['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": garrik_cid,
            "char_id": garrik["id"],
            "name": garrik["name"],
            "initiative": 10,
            "hp_current": 85, "hp_max": 85,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": garrik_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == garrik["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, "expected attack_targeted prompt for Garrik"
    keys = [o.get("key") for o in prompts[0]["data"].get("options", [])]
    assert "use-lucky" in keys, (
        f"expected use-lucky option; got {keys}"
    )
    lucky_opt = next(
        (o for o in prompts[0]["data"]["options"]
         if o.get("key") == "use-lucky"), {}
    )
    # Garrik long-rested → 3 charges before spending.
    assert int((lucky_opt.get("params") or {}).get("charges_before") or 0) == 3


async def test_use_lucky_decrements_charge(
    gm_client, gm_ws, roster,
):
    """End-to-end: Krieger hits Garrik → prompt fires → POST
    /use_reaction with use-lucky → Garrik's reaction flips +
    charges_after = 2 + feature_used(source=lucky).
    """
    garrik = roster["Garrik Ironside"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )

    garrik_cid = f"tok_lk2_{garrik['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": garrik_cid,
            "char_id": garrik["id"],
            "name": garrik["name"],
            "initiative": 10,
            "hp_current": 85, "hp_max": 85,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": garrik_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == garrik["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, "expected attack_targeted prompt for Garrik"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "use-lucky",
            "watcher_char_id": garrik["id"],
        },
    )
    assert use.status_code == 200, use.text

    await asyncio.sleep(0.2)
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == garrik["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Garrik's reaction"
    assert econ[-1]["data"]["used"] is True

    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "lucky"
        and (m.get("data") or {}).get("character_id") == garrik["id"]
    ]
    assert fu, "expected feature_used(source=lucky)"
    assert fu[-1]["data"].get("charges_after") == 2


# ── v2.76.0 — Phase 4c: War Caster feat ──


async def test_war_caster_prompt_offers_cast_alongside_oa(
    gm_client, gm_ws, roster,
):
    """v2.76.0 — when a creature exits the reach of a PC with the
    War Caster feat, the existing OA prompt (creature_exits_reach)
    now also surfaces a `take-war-caster-cast` option alongside the
    standard `take-the-oa`. Tavik got the feat in the v2.76.0 demo
    seed; his cleric spell list satisfies the at-least-one-1-action-
    spell gate.
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
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == tavik["id"]
        and (m.get("data") or {}).get("trigger_event")
        == "creature_exits_reach"
    ]
    assert prompts, "expected creature_exits_reach prompt for Tavik"
    options = prompts[0]["data"].get("options", [])
    keys = [o.get("key") for o in options]
    assert _oa_keys(options), f"expected a take-the-oa[:idx] option; got {keys}"
    assert "take-war-caster-cast" in keys, (
        f"expected take-war-caster-cast option alongside the OA; "
        f"got {keys}"
    )


async def test_use_war_caster_cast_marks_reaction(
    gm_client, gm_ws, roster,
):
    """End-to-end: Krieger leaves Tavik's reach → prompt fires →
    POST /use_reaction with take-war-caster-cast → Tavik's reaction
    flips + feature_used(source=war-caster) broadcast names the
    provoker (Krieger) + a click-Cast-Spell instruction.
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
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == tavik["id"]
        and (m.get("data") or {}).get("trigger_event")
        == "creature_exits_reach"
    ]
    assert prompts, "expected creature_exits_reach prompt for Tavik"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "take-war-caster-cast",
            "watcher_char_id": tavik["id"],
        },
    )
    assert use.status_code == 200, use.text

    await asyncio.sleep(0.2)
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == tavik["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Tavik's reaction"
    assert econ[-1]["data"]["used"] is True

    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "war-caster"
        and (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert fu, "expected feature_used(source=war-caster)"
    last = fu[-1]["data"]
    assert (last.get("provoker_name") or "").lower() == krieger["name"].lower()


# ── v2.75.0 — Phase 4d: Mage Slayer feat ──


async def test_mage_slayer_prompt_fires_on_spell_within_5ft(
    gm_client, gm_ws, roster,
):
    """v2.75.0 — when a creature within 5 ft of a PC with Mage Slayer
    casts a spell, the v2.70.0 `spell_cast_near` walker now also
    emits for that watcher (was: Counterspell-only). Krieger got the
    feat in the v2.75.0 demo seed; place Magnus 5 ft away and have
    him cast Burning Hands.
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    # Place tokens 5 ft apart (one cell at 70 px/cell).
    await _place_token(gm_client, magnus["id"], 300.0, 300.0)
    await _place_token(gm_client, krieger["id"], 370.0, 300.0)

    krieg_cid = f"tok_ms_kr_{krieger['id']}"
    magnus_cid = f"tok_ms_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        {
            "id": magnus_cid,
            "char_id": magnus["id"],
            "name": magnus["name"],
            "initiative": 14,
            "hp_current": 50, "hp_max": 50,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
        {
            "id": krieg_cid,
            "char_id": krieger["id"],
            "name": krieger["name"],
            "initiative": 10,
            "hp_current": 75, "hp_max": 75,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Magnus casts Burning Hands (index 5) at L3 (his only slot) —
    # action-time, doesn't trigger Counterspell from Magnus himself.
    # target_combatant_ids targets Krieger so the cast resolves.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": magnus["id"],
            "spell_index": 5,
            "slot_level": 3,
            "class_slug": "warlock",
            "target_combatant_ids": [krieg_cid],
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == krieger["id"]
        and (m.get("data") or {}).get("trigger_event") == "spell_cast_near"
    ]
    assert prompts, (
        f"expected reaction_prompt(spell_cast_near) for Krieger; "
        f"buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    keys = [o.get("key") for o in prompts[0]["data"].get("options", [])]
    assert "take-mage-slayer-strike" in keys, (
        f"expected take-mage-slayer-strike option; got {keys}"
    )


async def test_use_mage_slayer_strike_marks_reaction(
    gm_client, gm_ws, roster,
):
    """End-to-end: Magnus casts within 5 ft → Krieger's prompt fires
    → POST /use_reaction with take-mage-slayer-strike → Krieger's
    reaction flips + feature_used(source=mage-slayer) fires naming
    the caster + spell.
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    await _place_token(gm_client, magnus["id"], 300.0, 300.0)
    await _place_token(gm_client, krieger["id"], 370.0, 300.0)

    krieg_cid = f"tok_ms2_kr_{krieger['id']}"
    magnus_cid = f"tok_ms2_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        {
            "id": magnus_cid,
            "char_id": magnus["id"],
            "name": magnus["name"],
            "initiative": 14,
            "hp_current": 50, "hp_max": 50,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
        {
            "id": krieg_cid,
            "char_id": krieger["id"],
            "name": krieger["name"],
            "initiative": 10,
            "hp_current": 75, "hp_max": 75,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": magnus["id"],
            "spell_index": 5,
            "slot_level": 3,
            "class_slug": "warlock",
            "target_combatant_ids": [krieg_cid],
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == krieger["id"]
        and (m.get("data") or {}).get("trigger_event") == "spell_cast_near"
    ]
    assert prompts, "expected spell_cast_near prompt for Krieger"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "take-mage-slayer-strike",
            "watcher_char_id": krieger["id"],
        },
    )
    assert use.status_code == 200, use.text

    await asyncio.sleep(0.2)
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == krieger["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Krieger's reaction"
    assert econ[-1]["data"]["used"] is True

    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "mage-slayer"
        and (m.get("data") or {}).get("character_id") == krieger["id"]
    ]
    assert fu, "expected feature_used(source=mage-slayer)"
    last = fu[-1]["data"]
    assert (last.get("caster_name") or "").lower() == magnus["name"].lower()
    assert (last.get("spell_name") or "").lower() == "burning hands"


# ── v2.74.0 — Phase 4a: Defensive Duelist feat ──


async def test_defensive_duelist_prompt_fires_on_pc_hit(
    gm_client, gm_ws, roster,
):
    """v2.74.0 — when a PC with Defensive Duelist + an equipped
    finesse weapon is hit by a melee attack, the v2.69.0
    `attack_targeted` prompt now also surfaces `use-defensive-duelist`
    alongside any Shield option. Lyra got the feat in the v2.74.0
    demo seed (Rapier is finesse). Picked Lyra over Pip because
    Pip's Uncanny Dodge auto-fires on damage and burns the reaction
    before the prompt can offer DD.
    """
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]

    lyra_cid = f"tok_dd_{lyra['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": lyra_cid,
            "char_id": lyra["id"],
            "name": lyra["name"],
            "initiative": 10,
            "hp_current": 40, "hp_max": 40,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Probe until Krieger hits Lyra.
    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": lyra_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == lyra["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, (
        f"expected reaction_prompt(attack_targeted) for Lyra; "
        f"buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    keys = [o.get("key") for o in prompts[0]["data"].get("options", [])]
    assert "use-defensive-duelist" in keys, (
        f"expected use-defensive-duelist option; got {keys}"
    )
    dd_option = next(
        (o for o in prompts[0]["data"]["options"]
         if o.get("key") == "use-defensive-duelist"), {}
    )
    # Lyra is Bard 6 → PB +3.
    assert int((dd_option.get("params") or {}).get("pb") or 0) == 3


async def test_use_defensive_duelist_marks_reaction(
    gm_client, gm_ws, roster,
):
    """End-to-end: Krieger hits Lyra → prompt fires → POST
    /use_reaction with use-defensive-duelist → Lyra's reaction flips
    + feature_used(source=defensive-duelist, pb_bonus=3) broadcast.
    """
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]

    lyra_cid = f"tok_dd2_{lyra['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": lyra_cid,
            "char_id": lyra["id"],
            "name": lyra["name"],
            "initiative": 10,
            "hp_current": 40, "hp_max": 40,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": lyra_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == lyra["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, "expected attack_targeted prompt for Lyra"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "use-defensive-duelist",
            "watcher_char_id": lyra["id"],
        },
    )
    assert use.status_code == 200, use.text

    await asyncio.sleep(0.2)
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == lyra["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Lyra's reaction"
    assert econ[-1]["data"]["used"] is True

    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "defensive-duelist"
        and (m.get("data") or {}).get("character_id") == lyra["id"]
    ]
    assert fu, "expected feature_used(source=defensive-duelist)"
    assert fu[-1]["data"].get("pb_bonus") == 3


async def test_defensive_duelist_auto_negates_in_band_hit(
    gm_client, gm_ws, roster,
):
    """v2.601.0 — same retroactive-HP-restore recipe as v2.600.0
    Shield, but +PB AC instead of +5. When the +3 AC (Lyra is Bard 6,
    PB +3) turns a non-crit hit into a miss
    (target_ac <= attack_total < target_ac + 3), using Defensive
    Duelist via the prompt restores the full applied damage. Probes
    Krieger swings until an in-band non-crit hit lands, healing Lyra
    back to full between probes.
    """
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]
    await _set_auto_apply(gm_client, True)

    lyra_cid = f"tok_dd_negate_{lyra['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": lyra_cid,
            "char_id": lyra["id"],
            "name": lyra["name"],
            "initiative": 10,
            "hp_current": 40, "hp_max": 40,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Probe until a non-crit hit lands in the +PB negation band.
    in_band = None
    for _ in range(60):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": lyra_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        d = resp.json()
        atk_total = d.get("attack_total")
        target_ac = d.get("target_ac")
        if (
            d.get("hit")
            and not d.get("is_crit")
            and int(d.get("damage_applied") or 0) > 0
            and isinstance(atk_total, int)
            and isinstance(target_ac, int)
            and atk_total < target_ac + 3
        ):
            in_band = d
            break
        # Heal Lyra back to full between probes so each swing starts
        # from the same HP and we don't drop her to 0.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
            json={"type": "long"},
        )
    assert in_band is not None, (
        "no in-band (negatable, non-crit) hit landed in 60 swings"
    )
    dmg = int(in_band["damage_applied"])

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == lyra["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, "expected attack_targeted prompt for Lyra"
    prompt_id = prompts[-1]["data"]["prompt_id"]

    gm_ws.mark()
    use = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "use-defensive-duelist",
            "watcher_char_id": lyra["id"],
        },
    )
    assert use.status_code == 200, use.text
    await asyncio.sleep(0.2)

    neg = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "defensive-duelist-negate"
        and (m.get("data") or {}).get("character_id") == lyra["id"]
    ]
    assert neg, (
        f"expected feature_used(source=defensive-duelist-negate); got "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )
    assert int(neg[-1]["data"].get("heal_back") or 0) == dmg

    hp_up = [
        m for m in gm_ws.buffered("character_hp_update")
        if (m.get("data") or {}).get("character_id") == lyra["id"]
        and (m.get("data") or {}).get("source") == "defensive-duelist-negate"
    ]
    assert hp_up, "expected character_hp_update(source=defensive-duelist-negate)"
    assert int(hp_up[-1]["data"].get("delta") or 0) == dmg


# ── v2.73.0 — Phase 6: NPC monster reactions ──


async def test_npc_parry_prompt_fires_on_hit(
    gm_client, gm_ws, roster,
):
    """v2.73.0 — when a PC hits an NPC whose stat block has a
    `category: "reaction"` action (e.g. Bandit Captain's Parry),
    `/attack` emits a `reaction_prompt(attack_targeted)` with a
    `monster-parry` option. The NPC catalog reads
    `_monster_template_to_sheet(tmpl).actions[].category == "reaction"`.
    """
    krieger = roster["Krieger Stonefist"]
    # v2.79.0 — auto_apply_damage default is True via demo seed;
    # toggle dance removed after the v2.67.2 UD test fix.

    tmpl_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/templates",
        json={
            "name": "Bandit Captain (Parry trigger test)",
            "template": "dnd5e",
            "tags": ["npc", "harness"],
            "sheet": {"monster_slug": "bandit-captain"},
        },
    )
    assert tmpl_resp.status_code == 200, tmpl_resp.text
    tmpl = tmpl_resp.json()
    tok_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={
            "token_template_id": tmpl["id"],
            "label": "Bandit Captain",
            "x": 350.0, "y": 350.0,
            "color": "#822222", "size": 1,
        },
    )
    assert tok_resp.status_code == 200, tok_resp.text
    bc_tok = tok_resp.json()

    bc_cid = f"tok_npc_parry_{tmpl['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": bc_cid,
            "char_id": None,
            "source_token_id": bc_tok["id"],
            "token_template_id": tmpl["id"],
            "name": "Bandit Captain",
            "initiative": 9,
            "hp_current": 65, "hp_max": 65,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Probe until Krieger hits the captain.
    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": bc_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_combatant_id") == bc_cid
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, (
        f"expected reaction_prompt(attack_targeted) for Bandit Captain; "
        f"buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    keys = [o.get("key") for o in prompts[0]["data"].get("options", [])]
    assert "monster-parry" in keys, (
        f"expected monster-parry option; got {keys}"
    )


async def test_use_npc_parry_marks_reaction(
    gm_client, gm_ws, roster,
):
    """End-to-end: Krieger hits Bandit Captain → prompt fires → POST
    /use_reaction with monster-parry → Bandit Captain's reaction
    flips True via combatant_id + feature_used(source=monster-reaction)
    fires naming the action + monster.
    """
    krieger = roster["Krieger Stonefist"]
    # v2.79.0 — auto_apply_damage default is True via demo seed.

    tmpl_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/templates",
        json={
            "name": "Bandit Captain (Parry use test)",
            "template": "dnd5e",
            "tags": ["npc", "harness"],
            "sheet": {"monster_slug": "bandit-captain"},
        },
    )
    tmpl = tmpl_resp.json()
    tok_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={
            "token_template_id": tmpl["id"],
            "label": "Bandit Captain",
            "x": 350.0, "y": 350.0,
            "color": "#822222", "size": 1,
        },
    )
    bc_tok = tok_resp.json()

    bc_cid = f"tok_npc_parry2_{tmpl['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": bc_cid,
            "char_id": None,
            "source_token_id": bc_tok["id"],
            "token_template_id": tmpl["id"],
            "name": "Bandit Captain",
            "initiative": 9,
            "hp_current": 65, "hp_max": 65,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": bc_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 20 swings")
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_combatant_id") == bc_cid
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, "expected attack_targeted prompt for Bandit Captain"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    # NPC reactions don't carry a watcher_char_id.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "monster-parry",
        },
    )
    assert cast.status_code == 200, cast.text

    await asyncio.sleep(0.2)
    # economy_update for the NPC combatant (carries combatant_id,
    # not character_id since this is an NPC).
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("combatant_id") == bc_cid
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, (
        f"expected economy_update for Bandit Captain's reaction; "
        f"buffered: {[m.get('data') for m in gm_ws.buffered('economy_update')]}"
    )
    assert econ[-1]["data"]["used"] is True

    # feature_used(source=monster-reaction) names Parry + Bandit Captain.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "monster-reaction"
    ]
    assert fu, "expected feature_used(source=monster-reaction)"
    last = fu[-1]["data"]
    assert last.get("action_name") == "Parry"
    assert (last.get("monster_name") or "").lower().startswith("bandit captain")


# ── v2.72.0 — Phase 3d: Silvery Barbs ──


async def test_silvery_barbs_prompt_fires_on_save_pass(
    gm_client, gm_ws, roster,
):
    """v2.72.0 — when a creature succeeds on a save (DC met by the
    rolled d20+mod), a `save_resolved` event fires for every PC
    watcher who has Silvery Barbs prepared + a 1st+ slot + reaction
    unused (excluding the rolling character themselves). Thalindra
    has SB on her sheet via v2.72.0 demo seed addition; Krieger
    rolls a STR save against a DC 5 (trivially passes) so the trigger
    fires.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )

    thal_cid = f"tok_sb_{thalindra['id']}"
    krieg_cid = f"tok_sb_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        {
            "id": krieg_cid,
            "char_id": krieger["id"],
            "name": krieger["name"],
            "initiative": 12,
            "hp_current": 75, "hp_max": 75,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
        {
            "id": thal_cid,
            "char_id": thalindra["id"],
            "name": thalindra["name"],
            "initiative": 10,
            "hp_current": 32, "hp_max": 32,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Create a STR-save roll request with DC 5 so Krieger trivially
    # passes (he's a Barbarian — +7 STR save mod).
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request",
        json={
            "label": "STR save",
            "base_expression": "1d20",
            "stat_key": "str_save",
            "dc": 5,
            "visibility": "public",
        },
    )
    assert rr.status_code == 200, rr.text
    req_id = rr.json()["id"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request/{req_id}/respond",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "save_resolved"
    ]
    assert prompts, (
        f"expected reaction_prompt(save_resolved) for Thalindra; "
        f"buffered: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in _prompt_broadcasts(gm_ws)]}"
    )
    options = prompts[0]["data"].get("options", []) or []
    keys = [o.get("key") for o in options]
    assert "cast-silvery-barbs" in keys, (
        f"expected cast-silvery-barbs option; got {keys}"
    )
    sb_option = next(
        (o for o in options if o.get("key") == "cast-silvery-barbs"), {}
    )
    params = sb_option.get("params") or {}
    assert int(params.get("slot_level") or 0) == 1
    assert (params.get("target_name") or "").lower() == krieger["name"].lower()


async def test_cast_silvery_barbs_consumes_slot(
    gm_client, gm_ws, roster,
):
    """End-to-end: Krieger passes save → Thalindra's prompt fires →
    POST /use_reaction with cast-silvery-barbs → Thalindra's L1 slot
    used count increments + reaction flips + feature_used(source=
    silvery-barbs-cast) fires.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )

    thal_cid = f"tok_sb2_{thalindra['id']}"
    krieg_cid = f"tok_sb2_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        {
            "id": krieg_cid,
            "char_id": krieger["id"],
            "name": krieger["name"],
            "initiative": 12,
            "hp_current": 75, "hp_max": 75,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
        {
            "id": thal_cid,
            "char_id": thalindra["id"],
            "name": thalindra["name"],
            "initiative": 10,
            "hp_current": 32, "hp_max": 32,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request",
        json={
            "label": "STR save",
            "base_expression": "1d20",
            "stat_key": "str_save",
            "dc": 5,
            "visibility": "public",
        },
    )
    req_id = rr.json()["id"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll_request/{req_id}/respond",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 200, resp.text
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "save_resolved"
    ]
    assert prompts, "expected save_resolved prompt for Thalindra"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "cast-silvery-barbs",
            "watcher_char_id": thalindra["id"],
        },
    )
    assert cast.status_code == 200, cast.text

    await asyncio.sleep(0.2)
    # economy_update: reaction flipped.
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Thalindra's reaction"
    assert econ[-1]["data"]["used"] is True

    # spell_slot_update: L1 wizard slot decremented.
    slot_msgs = [
        m for m in gm_ws.buffered("spell_slot_update")
        if (m.get("data") or {}).get("character_id") == thalindra["id"]
        and int((m.get("data") or {}).get("level") or 0) == 1
    ]
    assert slot_msgs, (
        f"expected spell_slot_update L1 for Thalindra; "
        f"buffered: {[m.get('data') for m in gm_ws.buffered('spell_slot_update')]}"
    )

    # feature_used(source=silvery-barbs-cast) fires.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "silvery-barbs-cast"
        and (m.get("data") or {}).get("character_id") == thalindra["id"]
    ]
    assert fu, "expected feature_used(source=silvery-barbs-cast)"
    last = fu[-1]["data"]
    assert last.get("slot_level") == 1
    assert (last.get("rerolled_target_name") or "").lower() == krieger["name"].lower()


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
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
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
    oa_key = _first_oa_key(prompts[0]["data"].get("options"))

    gm_ws.mark()
    # GM resolves the NPC reaction. watcher_char_id intentionally
    # omitted — NPCs don't have one.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": oa_key,
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


# ── v2.97.24 — buff teardown for the 2 reaction-cast buff installers ──


async def test_cast_shield_undo_refunds_slot_and_drops_buff(
    gm_client, gm_ws, roster,
):
    """v2.97.24 — Shield undo refunds the slot AND drops the
    shield-active buff. Pre-v2.97.24 the slot refunded but the
    buff stayed installed."""
    krieger = roster["Krieger Stonefist"]
    thalindra = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )

    thal_cid = f"tok_shield_undo_{thalindra['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": thal_cid,
            "char_id": thalindra["id"],
            "name": thalindra["name"],
            "initiative": 10,
            "hp_current": 32, "hp_max": 32,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    for _ in range(20):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,
                "target_combatant_id": thal_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed")
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == thalindra["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "cast-shield",
            "watcher_char_id": thalindra["id"],
        },
    )
    assert cast.status_code == 200

    await asyncio.sleep(0.2)
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "shield-cast"
    ]
    assert fu
    cast_id = fu[-1]["data"].get("cast_id")
    assert cast_id

    # Buff IS installed.
    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "shield-active" for b in buffs)

    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": cast_id},
    )
    assert undo.status_code == 200, undo.text
    kinds = {e.get("kind") for e in (undo.json().get("per_target") or [])}
    assert "spell_slot_refunded" in kinds
    assert "buff_install" in kinds

    buffs2 = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/buffs"
    )).json().get("buffs", [])
    assert not any((b or {}).get("key") == "shield-active" for b in buffs2), (
        f"shield-active still installed after undo: {buffs2}"
    )
