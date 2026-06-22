"""v2.66.0 — F1 follow-ups: Opportunity Attack trigger + Aura conscious-check.

Closes two v1 simplifications from v2.61.0:

(A) Aura of Protection / Aura of Devotion require the paladin to be
    conscious (RAW). Pre-v2.66.0 the auras fired even if the paladin
    was at 0 HP / dying. v2.66.0 adds ``_paladin_is_conscious`` and
    gates both auras on it.

(B) Opportunity Attack RAW: when a hostile creature moves out of your
    reach, you can use your reaction to make a melee attack. v2.66.0
    detects the transition (within reach at from_pos → out of reach
    at to_pos) and broadcasts a feature_used advisory naming the
    watcher + the provoking mover. Pure advisory — does NOT consume
    the reaction or fire the attack.

Tests:
  - Aura skips when Caelan is set to "dying" via death-save override.
  - OA trigger fires when a token moves out of a watcher's 5 ft reach.
  - OA does NOT fire when the watcher's reaction is already used.
  - OA does NOT fire when the move is from out-of-reach (no provocation).

Demo grid: 70 px / cell, 5 ft / cell.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


FIREBALL_INDEX = 10  # Fireball, DEX save (stored-sheet index; 7 drifted to
                     # Web — see test_cast_spell_aoe.py).


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


def _make_combatant(name, char_id, init=10, hp=40):
    return {
        "id": f"tok_oa_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {
            "action": False, "bonus": False, "reaction": False, "movement": 0,
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


def _aop_broadcasts(gm_ws, paladin_char_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "aura-of-protection"
        and (m.get("data") or {}).get("character_id") == paladin_char_id
    ]


def _roll_request_broadcast(gm_ws):
    msgs = gm_ws.buffered("roll_request")
    return msgs[-1] if msgs else None


async def test_aura_of_protection_skips_when_paladin_unconscious(
    gm_client, gm_ws, roster, thalindra_rested,
):
    """v2.66.0 — Aura conscious-check.

    Setup: Thalindra + Caelan + Pip in init. Override Caelan's death-
    save status to ``dying`` so ``_paladin_is_conscious`` returns
    False. Cast Fireball at Pip → Pip's save base_expression should
    be plain "1d20" (no +CHA from Caelan) AND no aura broadcast fires.
    """
    thal = thalindra_rested
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]

    # Drive Caelan to dying via the GM override endpoint. This sets
    # death_saves.status = "dying" and HP → 0 implicitly.
    override = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/death-save/override",
        json={"status": "dying"},
    )
    assert override.status_code == 200, override.text

    try:
        await _seed_battle(gm_client, [
            _make_combatant(thal["name"], thal["id"], init=12),
            _make_combatant(caelan["name"], caelan["id"], init=10),
            _make_combatant(pip["name"], pip["id"], init=8),
        ])
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": FIREBALL_INDEX,
                "slot_level": 3,
                "class_slug": "wizard",
                "target_combatant_id": f"tok_oa_{pip['id']}",
                "target_character_id": pip["id"],
                "target_name": pip["name"],
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text

        rr = _roll_request_broadcast(gm_ws)
        assert rr is not None, "expected a roll_request broadcast for Pip"
        assert rr["data"]["base_expression"] == "1d20", (
            f"Aura should NOT fire from a dying paladin; expected "
            f"base_expression='1d20', got {rr['data']['base_expression']!r}"
        )
        aura_msgs = _aop_broadcasts(gm_ws, caelan["id"])
        assert not aura_msgs, (
            f"no Aura broadcast should fire when Caelan is dying; got: "
            f"{[m.get('data') for m in aura_msgs]}"
        )
    finally:
        # Restore Caelan to alive so subsequent tests get a clean state.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/death-save/override",
            json={"status": "alive", "successes": 0, "failures": 0},
        )


async def _tokens_by_char(client) -> dict[int, dict]:
    resp = await client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    by_char = {}
    for t in data["tokens"]:
        if t.get("character_id"):
            by_char[t["character_id"]] = t
    return by_char


async def _set_token_pos(gm_client, token_id: int, x: float, y: float):
    """Setup move: drop a token to a known position WITHOUT triggering
    an OA broadcast in the buffered WS messages we care about. We
    clear the WS buffer after via gm_ws.mark() in the calling test.

    v2.99.55 — always passes ``oa_confirmed: True`` so the v2.99.55
    Phase 4 gate doesn't 409 on a setup move that happens to cross
    a watcher's reach. Setup moves are GM-authored and aren't
    subject to the pre-move modal.
    """
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}/move",
        json={"x": float(x), "y": float(y), "oa_confirmed": True},
    )
    assert r.status_code == 200, r.text


async def _place_token(gm_client, char_id: int, x: float, y: float):
    """Ensure the character has a token at (x, y) on the active map.
    Robust against prior tests (e.g. test_aura_range_gate.py) that
    deleted the token in cleanup. Returns the placed token dict.
    """
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _get_token_for_char(gm_client, char_id: int):
    tokens = await _tokens_by_char(gm_client)
    return tokens.get(char_id)


def _oa_broadcasts(gm_ws) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "opportunity-attack-trigger"
    ]


async def test_oa_fires_when_mover_leaves_watcher_reach(
    gm_client, gm_ws, roster,
):
    """Krieger token starts at (350, 350) — Tavik watcher at
    (420, 350) (1 cell = 5 ft away, within reach). Move Krieger to
    (700, 350) (5 cells = 25 ft from Tavik, beyond reach). Assert:

      - move response carries an ``opportunity_attack_triggers`` list
        with Tavik as the watcher,
      - a ``feature_used(source="opportunity-attack-trigger")``
        broadcast names Tavik.

    Reaction is NOT consumed — this is advisory only.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])

    # Ensure tokens exist on the active map. Prior tests
    # (test_aura_range_gate.py) delete tokens in cleanup, so we
    # re-place rather than rely on the demo seed.
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    tv_tok = await _get_token_for_char(gm_client, tavik["id"])
    assert kr_tok and tv_tok, "tokens must exist after place"

    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Move Krieger 5 cells right → 25 ft from Tavik.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    triggers = data.get("opportunity_attack_triggers") or []
    matching = [
        t for t in triggers
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert matching, (
        f"expected an OA trigger naming Tavik; got triggers={triggers}"
    )
    assert matching[0].get("watcher_name") == tavik["name"]

    # WS broadcast asserts.
    await asyncio.sleep(0.15)
    oa_msgs = _oa_broadcasts(gm_ws)
    tv_msgs = [
        m for m in oa_msgs
        if (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert tv_msgs, (
        f"expected feature_used(source=opportunity-attack-trigger) for "
        f"Tavik; buffered: "
        f"{[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_oa_skips_when_watcher_reaction_used(
    gm_client, gm_ws, roster,
):
    """When the watcher's reaction is already used this round, no OA
    trigger fires — RAW: OA needs a reaction.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    tavik_combatant = _make_combatant(tavik["name"], tavik["id"], init=8)
    # Mark reaction as used.
    tavik_combatant["economy"]["reaction"] = True
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        tavik_combatant,
    ])

    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok, "Krieger token must exist after place"
    await asyncio.sleep(0.15)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert not triggers, (
        f"OA trigger should NOT fire when Tavik's reaction is used; "
        f"got {triggers}"
    )


async def test_oa_skips_when_move_starts_out_of_reach(
    gm_client, gm_ws, roster,
):
    """No provocation when the mover starts OUT of reach — OA only
    fires on the transition from within-reach to out-of-reach.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])

    # Krieger starts 25 ft (5 cells) from Tavik — out of reach.
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 700.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok, "Krieger token must exist after place"
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Move Krieger further away — still no transition through reach.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 280.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert not triggers, (
        f"OA trigger should NOT fire when start position is already "
        f"out of reach; got {triggers}"
    )


async def test_oa_honors_explicit_melee_reach_ft_override(
    gm_client, gm_ws, roster,
):
    """v2.66.1 — reach-weapon support. Tavik combatant seeded with
    ``melee_reach_ft=10`` (glaive / halberd / hill-giant-style reach).
    Krieger starts 10 ft (2 cells = 140 px) away — IN range; moves to
    15 ft (3 cells = 210 px) — OUT of range. OA should fire on this
    transition past the 10 ft threshold, even though the previous v1
    hardcoded 5 ft would have skipped it (5 ft → already out by 10 ft
    start).
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    tavik_combatant = _make_combatant(tavik["name"], tavik["id"], init=8)
    # GM marks Tavik as wielding a reach weapon (10 ft threat zone).
    tavik_combatant["melee_reach_ft"] = 10.0
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        tavik_combatant,
    ])

    # Place Tavik at (350, 350). Krieger at (490, 350) — 140 px away
    # = 2 cells = 10 ft → within Tavik's reach.
    await _place_token(gm_client, tavik["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 490.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok, "Krieger token must exist after place"
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Move Krieger 1 cell further → (560, 350), distance = 3 cells
    # = 15 ft from Tavik. Past the 10 ft threshold → OA.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 560.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    matching = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert matching, (
        f"expected OA trigger with 10 ft reach override; "
        f"got triggers={data.get('opportunity_attack_triggers')}"
    )
    assert matching[0].get("watcher_reach_ft") == 10.0, (
        f"trigger should carry watcher_reach_ft=10.0; got "
        f"{matching[0].get('watcher_reach_ft')!r}"
    )

    # WS broadcast should mention the 10 ft reach in feature_desc.
    await asyncio.sleep(0.15)
    oa_msgs = _oa_broadcasts(gm_ws)
    tv_msgs = [
        m for m in oa_msgs
        if (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert tv_msgs, "expected OA broadcast for Tavik"
    desc = (tv_msgs[0].get("data") or {}).get("feature_desc") or ""
    assert "10 ft" in desc, (
        f"broadcast desc should reference 10 ft reach; got {desc!r}"
    )


async def test_oa_5ft_reach_still_skips_at_10ft_start(
    gm_client, gm_ws, roster,
):
    """Control: a standard-reach (5 ft) watcher does NOT fire OA when
    the mover starts 10 ft away (already out of reach). Confirms the
    reach helper still defaults to 5 ft when no override is set —
    only an explicit override or a sheet-derived reach weapon pushes
    the threshold up.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])

    # 10 ft (2 cells) apart — outside default 5 ft reach.
    await _place_token(gm_client, tavik["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 490.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok, "Krieger token must exist"
    await asyncio.sleep(0.15)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 560.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    matching = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert not matching, (
        f"default 5 ft reach should NOT trigger at 10 ft start; "
        f"got {matching}"
    )


async def test_oa_npc_reach_parses_from_monster_action_desc(
    gm_client, gm_ws, roster,
):
    """v2.66.2 — NPC reach parsed from monster action ``desc`` text.

    Creates a Hill Giant TokenTemplate (SRD slug ``hill-giant`` has
    "reach 10 ft." in its Greatclub action), spawns a token, and
    seeds the battle with the Hill Giant watching Krieger. Krieger
    starts 10 ft (2 cells) from the giant, moves to 15 ft (3 cells).
    OA should fire because the helper extracted reach=10 from the
    giant's action desc — no explicit ``melee_reach_ft`` set.
    """
    krieger = roster["Krieger Stonefist"]

    # Create a Hill Giant template (pointer to SRD slug).
    tmpl_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/templates",
        json={
            "name": "Hill Giant (OA test)",
            "template": "dnd5e",
            "tags": ["npc", "harness"],
            "sheet": {"monster_slug": "hill-giant"},
        },
    )
    assert tmpl_resp.status_code == 200, tmpl_resp.text
    tmpl = tmpl_resp.json()

    # Spawn a token from that template at (350, 350).
    tok_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={
            "token_template_id": tmpl["id"],
            "label": "Hill Giant",
            "x": 350.0,
            "y": 350.0,
            "color": "#9c884a",
            "size": 2,
        },
    )
    assert tok_resp.status_code == 200, tok_resp.text
    giant_tok = tok_resp.json()

    # Place Krieger 10 ft (2 cells = 140 px) away — within the giant's
    # parsed 10 ft reach.
    await _place_token(gm_client, krieger["id"], 490.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok, "Krieger token must exist"

    # Seed a battle with both combatants. The Hill Giant is an NPC
    # combatant referencing the token via source_token_id (no char_id).
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        {
            "id": "tok_oa_giant",
            "char_id": None,
            "source_token_id": giant_tok["id"],
            "token_template_id": tmpl["id"],
            "name": "Hill Giant",
            "initiative": 8,
            "hp_current": 105, "hp_max": 105,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Move Krieger 1 cell further → 15 ft from the giant. Past the
    # 10 ft threshold → OA should fire because the helper parsed
    # "reach 10 ft." from the giant's Greatclub action desc.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 560.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    matching = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_combatant_id") == "tok_oa_giant"
    ]
    assert matching, (
        f"expected OA trigger from Hill Giant (10 ft reach parsed "
        f"from action desc); got triggers="
        f"{data.get('opportunity_attack_triggers')}"
    )
    assert matching[0].get("watcher_reach_ft") == 10.0, (
        f"trigger should carry watcher_reach_ft=10.0; got "
        f"{matching[0].get('watcher_reach_ft')!r}"
    )


async def test_oa_polearm_master_fires_on_enter_reach(
    gm_client, gm_ws, roster,
):
    """v2.66.4 — Polearm Master enter-reach OA. RAW: "While you are
    wielding a glaive, halberd, pike, quarterstaff, or spear, other
    creatures provoke an opportunity attack from you when they enter
    your reach."

    Tavik seeded with ``polearm_master=True`` and
    ``melee_reach_ft=10`` (glaive-wielding). Krieger starts 15 ft
    away (out of reach), moves to 10 ft (enters reach). OA should
    fire with trigger_type="enter" and the chat card should mention
    Polearm Master.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    tavik_combatant = _make_combatant(tavik["name"], tavik["id"], init=8)
    tavik_combatant["polearm_master"] = True
    tavik_combatant["melee_reach_ft"] = 10.0
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        tavik_combatant,
    ])

    # Tavik at (350, 350); Krieger starts at (560, 350) — 3 cells
    # = 15 ft away, OUT of Tavik's 10 ft reach.
    await _place_token(gm_client, tavik["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 560.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok, "Krieger token must exist"
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Move Krieger 1 cell closer → (490, 350), distance = 2 cells
    # = 10 ft → exactly within Tavik's 10 ft reach. Enter-reach
    # transition triggers Polearm Master OA.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 490.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    matching = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert matching, (
        f"expected Polearm Master enter-reach OA trigger; "
        f"got {data.get('opportunity_attack_triggers')}"
    )
    assert matching[0].get("trigger_type") == "enter", (
        f"trigger should carry trigger_type='enter'; got "
        f"{matching[0].get('trigger_type')!r}"
    )

    # Broadcast assertions.
    await asyncio.sleep(0.15)
    oa_msgs = _oa_broadcasts(gm_ws)
    tv_msgs = [
        m for m in oa_msgs
        if (m.get("data") or {}).get("character_id") == tavik["id"]
        and (m.get("data") or {}).get("trigger_type") == "enter"
    ]
    assert tv_msgs, (
        f"expected enter-reach feature_used broadcast for Tavik; "
        f"got: {[(m.get('data') or {}).get('trigger_type') for m in oa_msgs]}"
    )
    desc = (tv_msgs[0].get("data") or {}).get("feature_desc") or ""
    assert "Polearm Master" in desc, (
        f"broadcast desc should reference Polearm Master; got {desc!r}"
    )


async def test_oa_enter_reach_skips_without_polearm_master(
    gm_client, gm_ws, roster,
):
    """Control: same geometry as the Polearm Master test, but Tavik
    DOESN'T have the feat. Enter-reach transition should NOT fire
    an OA — only the standard exit-reach trigger covers normal
    combatants.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    # Reach 10 ft but no polearm_master flag.
    tavik_combatant = _make_combatant(tavik["name"], tavik["id"], init=8)
    tavik_combatant["melee_reach_ft"] = 10.0
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        tavik_combatant,
    ])

    await _place_token(gm_client, tavik["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 560.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok, "Krieger token must exist"
    await asyncio.sleep(0.15)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 490.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    matching = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert not matching, (
        f"enter-reach OA should NOT fire without Polearm Master; "
        f"got {matching}"
    )


# ── v2.66.5 — Sentinel feat (effect 3: ally attacked near you) ──


def _sentinel_broadcasts(gm_ws) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "sentinel-attack-trigger"
    ]


async def test_sentinel_fires_when_ally_attacks_target_near_watcher(
    gm_client, gm_ws, roster,
):
    """v2.66.5 — RAW Sentinel effect 3: "When a creature within 5 ft
    of you makes an attack against a target other than you (and that
    target doesn't have this feat), you can use your reaction to make
    a melee weapon attack against the attacking creature."

    Setup: Krieger (attacker) at (350, 350). Tavik (sentinel) at
    (420, 350) — 5 ft east of Krieger. Pip (target) at (350, 420) —
    5 ft south of Krieger, within Greataxe range. Krieger attacks Pip
    → Tavik is within 5 ft of the attacker (Krieger), not the target
    (Pip). Sentinel trigger fires.
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]

    tavik_combatant = _make_combatant(tavik["name"], tavik["id"], init=8)
    tavik_combatant["sentinel"] = True
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12),
        _make_combatant(pip["name"], pip["id"], init=10),
        tavik_combatant,
    ])

    # Place tokens. Krieger center; Tavik 5 ft east (sentinel watcher);
    # Pip 5 ft south (target — within Greataxe range).
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    await _place_token(gm_client, pip["id"], 350.0, 420.0)
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Find Pip's combatant id from the seeded battle.
    pip_combatant_id = f"tok_oa_{pip['id']}"

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,  # Greataxe
            "target_combatant_id": pip_combatant_id,
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in (data.get("sentinel_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert triggers, (
        f"expected Sentinel trigger naming Tavik; got "
        f"sentinel_triggers={data.get('sentinel_triggers')}"
    )

    # Broadcast assertion.
    await asyncio.sleep(0.2)
    sentinel_msgs = _sentinel_broadcasts(gm_ws)
    tv_msgs = [
        m for m in sentinel_msgs
        if (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert tv_msgs, (
        f"expected sentinel-attack-trigger broadcast for Tavik; "
        f"got: {[(m.get('data') or {}).get('character_name') for m in sentinel_msgs]}"
    )
    desc = (tv_msgs[0].get("data") or {}).get("feature_desc") or ""
    assert "Sentinel" in desc, (
        f"broadcast desc should reference Sentinel; got {desc!r}"
    )


async def test_sentinel_skips_when_watcher_is_the_target(
    gm_client, gm_ws, roster,
):
    """Control: RAW Sentinel doesn't fire when the watcher IS the
    target — the watcher would just take the attack normally.
    Tavik (sentinel) is the target this time; even though he's near
    himself, no trigger fires.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]

    tavik_combatant = _make_combatant(tavik["name"], tavik["id"], init=8)
    tavik_combatant["sentinel"] = True
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12),
        tavik_combatant,
    ])

    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    await asyncio.sleep(0.15)
    gm_ws.mark()

    tavik_combatant_id = f"tok_oa_{tavik['id']}"

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": tavik_combatant_id,
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in (data.get("sentinel_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert not triggers, (
        f"Sentinel should NOT fire when watcher IS the target; "
        f"got {triggers}"
    )


async def test_sentinel_skips_without_feat_flag(
    gm_client, gm_ws, roster,
):
    """Control: same geometry as the firing test but no sentinel
    flag → no broadcast.
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]

    # No `sentinel: True` on Tavik.
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12),
        _make_combatant(pip["name"], pip["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])

    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    await _place_token(gm_client, pip["id"], 350.0, 420.0)
    await asyncio.sleep(0.15)
    gm_ws.mark()

    pip_combatant_id = f"tok_oa_{pip['id']}"
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": pip_combatant_id,
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in (data.get("sentinel_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert not triggers, (
        f"Sentinel should NOT fire without the feat flag; got {triggers}"
    )


async def test_sentinel_fires_on_npc_attack(
    gm_client, gm_ws, roster,
):
    """v2.66.6 — Sentinel effect 3 wired into /npc_attack too. A
    bandit NPC strikes Pip; Tavik (PC sentinel) is 5 ft from the
    bandit. /npc_attack response carries sentinel_triggers + the
    feature_used broadcast fires.
    """
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]

    # Create a bandit template + token, place it at (350, 350).
    tmpl_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/templates",
        json={
            "name": "Bandit (Sentinel test)",
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
            "x": 350.0,
            "y": 350.0,
            "color": "#a23030",
            "size": 1,
        },
    )
    assert tok_resp.status_code == 200, tok_resp.text
    bandit_tok = tok_resp.json()

    # Place Tavik 5 ft east of the bandit; Pip 5 ft south (target).
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    await _place_token(gm_client, pip["id"], 350.0, 420.0)

    # Seed battle: bandit NPC (with source_token_id), Tavik (sentinel),
    # Pip (target). The bandit combatant has no char_id — pure NPC.
    bandit_combatant_id = "tok_oa_bandit_sent"
    tavik_combatant = _make_combatant(tavik["name"], tavik["id"], init=8)
    tavik_combatant["sentinel"] = True
    await _seed_battle(gm_client, [
        {
            "id": bandit_combatant_id,
            "char_id": None,
            "source_token_id": bandit_tok["id"],
            "token_template_id": tmpl["id"],
            "name": "Bandit",
            "initiative": 12,
            "hp_current": 11, "hp_max": 11,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
        _make_combatant(pip["name"], pip["id"], init=10),
        tavik_combatant,
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    pip_combatant_id = f"tok_oa_{pip['id']}"
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": bandit_combatant_id,
            "action_id": "scimitar",
            "action_name": "Scimitar",
            "attack_bonus": "+3",
            "damage": "1d6+1",
            "damage_type": "slashing",
            "range": "5 ft",
            "target_combatant_id": pip_combatant_id,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in (data.get("sentinel_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert triggers, (
        f"expected Sentinel trigger on NPC attack; got "
        f"sentinel_triggers={data.get('sentinel_triggers')}"
    )

    await asyncio.sleep(0.2)
    sentinel_msgs = _sentinel_broadcasts(gm_ws)
    tv_msgs = [
        m for m in sentinel_msgs
        if (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert tv_msgs, (
        f"expected sentinel-attack-trigger broadcast for Tavik on NPC "
        f"attack; got: "
        f"{[(m.get('data') or {}).get('character_name') for m in sentinel_msgs]}"
    )
    desc = (tv_msgs[0].get("data") or {}).get("feature_desc") or ""
    assert "Bandit" in desc, (
        f"broadcast desc should name the bandit attacker; got {desc!r}"
    )


# ── v2.99.52 — plan-movement-oa-flow Phase 1: same-team OA filter ──


async def _set_team(gm_client, token_id: int, team: str):
    """Helper: PATCH a token's team field via the v2.99.52 endpoint."""
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}",
        json={"team": team},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_oa_skips_when_mover_and_watcher_share_team(
    gm_client, gm_ws, roster,
):
    """v2.99.52: Krieger (hero) moves out of Tavik's (hero) reach →
    NO OA trigger fires. Same-team filter swallows the trigger.
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
    tv_tok = await _get_token_for_char(gm_client, tavik["id"])
    assert kr_tok and tv_tok, "tokens must exist"
    # Tag BOTH as hero.
    await _set_team(gm_client, kr_tok["id"], "hero")
    await _set_team(gm_client, tv_tok["id"], "hero")
    try:
        await asyncio.sleep(0.15)
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
            json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        triggers = data.get("opportunity_attack_triggers") or []
        assert not triggers, (
            f"same-team move should NOT trigger OA; got {triggers}"
        )
        await asyncio.sleep(0.15)
        oa_msgs = _oa_broadcasts(gm_ws)
        assert not oa_msgs, (
            f"same-team move should NOT broadcast OA advisory; got "
            f"{[(m.get('data') or {}).get('character_name') for m in oa_msgs]}"
        )
    finally:
        # Reset teams so subsequent tests start from a clean fixture.
        await _set_team(gm_client, kr_tok["id"], "neutral")
        await _set_team(gm_client, tv_tok["id"], "neutral")


async def test_oa_fires_when_mover_and_watcher_opposite_teams(
    gm_client, gm_ws, roster,
):
    """v2.99.52: Krieger (villain) moves out of Tavik's (hero) reach
    → OA trigger fires normally. Opposite teams don't filter.
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
    tv_tok = await _get_token_for_char(gm_client, tavik["id"])
    await _set_team(gm_client, kr_tok["id"], "villain")
    await _set_team(gm_client, tv_tok["id"], "hero")
    try:
        await asyncio.sleep(0.15)
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
            json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        triggers = [
            t for t in (data.get("opportunity_attack_triggers") or [])
            if t.get("watcher_char_id") == tavik["id"]
        ]
        assert triggers, (
            f"opposite-team OA should fire; got triggers="
            f"{data.get('opportunity_attack_triggers')}"
        )
    finally:
        await _set_team(gm_client, kr_tok["id"], "neutral")
        await _set_team(gm_client, tv_tok["id"], "neutral")


async def test_oa_fires_when_one_side_is_neutral(
    gm_client, gm_ws, roster,
):
    """v2.99.52: when EITHER side is neutral the filter doesn't fire
    — back-compat for campaigns that haven't tagged tokens yet. Mover
    is hero, watcher is neutral → OA fires.
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
    tv_tok = await _get_token_for_char(gm_client, tavik["id"])
    # Mover gets a team; watcher stays neutral.
    await _set_team(gm_client, kr_tok["id"], "hero")
    # tv_tok defaults to neutral; explicit set for clarity.
    await _set_team(gm_client, tv_tok["id"], "neutral")
    try:
        await asyncio.sleep(0.15)
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
            json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        triggers = [
            t for t in (data.get("opportunity_attack_triggers") or [])
            if t.get("watcher_char_id") == tavik["id"]
        ]
        assert triggers, (
            f"neutral-vs-tagged OA should still fire; got triggers="
            f"{data.get('opportunity_attack_triggers')}"
        )
    finally:
        await _set_team(gm_client, kr_tok["id"], "neutral")


# ── v2.99.62 — NPC watcher Token fallback (template + label) ──


async def test_oa_fires_for_npc_watcher_without_source_token_id(
    gm_client, gm_ws, roster,
):
    """v2.99.62 — regression test for the demo OA bug. The demo's
    seed_encounter populates NPC combatants with only
    ``token_template_id`` + ``name`` (no ``source_token_id``, no
    ``char_id``). Pre-v2.99.62 the OA helper's Token lookup tried
    source_token_id then char_id then gave up — silently skipping
    NPC watchers. v2.99.62's fallback matches by
    token_template_id + label on the active map.

    Geometry: Krieger at (350, 350). Bandit NPC at (420, 350) —
    5 ft east, in melee reach. Drag Krieger to (700, 350) — out
    of reach. The bandit is in init with only template + name
    (no source_token_id). OA should still fire.
    """
    krieger = roster["Krieger Stonefist"]

    # Create a bandit template + token.
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    tok_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={
            "token_template_id": bandit_tmpl["id"],
            "label": "Goon",
            "x": 420.0, "y": 350.0,
            "color": "#c84a4a",
            "size": 1,
        },
    )
    assert tok_resp.status_code == 200, tok_resp.text

    # Seed the battle with the NPC combatant WITHOUT source_token_id.
    # This is the demo's exact shape — token_template_id + name +
    # nothing linking to the Token row id.
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        {
            "id": "tok_npc_fallback_test",
            "char_id": None,
            "token_template_id": bandit_tmpl["id"],
            "name": "Goon",  # matches the Token row's label
            "initiative": 8,
            "hp_current": 11, "hp_max": 11,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
            # NO source_token_id field — this is the bug case
        },
    ])
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Drag Krieger out of the bandit's reach.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_combatant_id") == "tok_npc_fallback_test"
    ]
    assert triggers, (
        f"NPC fallback (token_template_id + label match) should have "
        f"surfaced the Goon's OA; got {data.get('opportunity_attack_triggers')}"
    )


# ── v2.99.60 — path-aware OA detection ──


async def test_oa_fires_on_path_cross_when_both_endpoints_outside_reach(
    gm_client, gm_ws, roster,
):
    """v2.99.60 — RAW: an OA fires "right before the creature leaves
    your reach." A mover that walks THROUGH a watcher's reach in
    one drag (starts OUT, passes within reach mid-segment, ends OUT)
    should still provoke an OA at the exit point. Pre-v2.99.60 the
    endpoint-only check missed this.

    Geometry: Tavik at (700, 350). Krieger starts at (350, 350) —
    5 cells (25 ft) west of Tavik, out of reach. Drag Krieger to
    (1050, 350) — 5 cells (25 ft) east of Tavik, also out of
    reach. The straight-line path passes RIGHT THROUGH Tavik's
    5 ft reach. Path-cross OA should fire.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 700.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    await asyncio.sleep(0.15)
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 1050.0, "y": 350.0, "oa_confirmed": True,
              "over_speed_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert triggers, (
        f"path-cross OA should fire for Tavik; got triggers="
        f"{data.get('opportunity_attack_triggers')}"
    )
    # The trigger should carry the new path_crossed_ft field.
    assert triggers[0].get("path_crossed_ft") is not None, (
        f"path-cross trigger should carry path_crossed_ft; got "
        f"{triggers[0]}"
    )
    # The path_crossed_ft (min distance from segment to watcher)
    # should be <= the watcher's 5 ft reach.
    assert triggers[0]["path_crossed_ft"] <= 5.0, (
        f"path_crossed_ft should be within reach; got "
        f"{triggers[0]['path_crossed_ft']}"
    )


async def test_oa_skips_path_cross_when_path_misses_reach(
    gm_client, roster,
):
    """v2.99.60 — control test for the path-cross logic. If the
    move path's minimum distance to the watcher is greater than
    their reach, no OA fires.

    Geometry: Tavik at (700, 700). Krieger at (350, 350); drag him
    to (1050, 350) — the path is far north of Tavik (well outside
    his 5 ft / 1-cell reach). No path-cross OA.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
    ])
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 700.0, 700.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    await asyncio.sleep(0.15)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 1050.0, "y": 350.0, "oa_confirmed": True,
              "over_speed_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in (data.get("opportunity_attack_triggers") or [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert not triggers, (
        f"path that misses reach should NOT fire OA; got {triggers}"
    )


# ── v2.99.59 — presence-aware popup routing ──


async def _move_krieger_past_pip(gm_client, krieger, pip):
    """Helper: place Krieger + Pip with Pip in melee reach, then move
    Krieger out of reach. Returns the move response JSON.
    """
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(pip["name"], pip["id"], init=8),
    ])
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, pip["id"], 420.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    await asyncio.sleep(0.15)
    return kr_tok


async def test_oa_prompt_routes_to_player_when_present(
    gm_client, gm_ws, alice_ws, roster,
):
    """v2.99.59: alice has an open WS connection (she's at the table).
    Krieger walks past her PC (Pip). The prompt's target_user_ids
    routes to alice ONLY — the GM is excluded so they don't get a
    duplicate popup the player is already handling.
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]  # owned by alice
    kr_tok = await _move_krieger_past_pip(gm_client, krieger, pip)
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    await asyncio.sleep(0.2)
    prompts = [
        m for m in gm_ws.buffered("reaction_prompt")
        if (m.get("data") or {}).get("watcher_char_id") == pip["id"]
    ]
    assert prompts, "expected reaction_prompt for Pip"
    targets = prompts[0]["data"].get("target_user_ids") or []
    pip_owner = pip.get("owner_user_id")
    assert pip_owner is not None, (
        "Pip's owner_user_id should be populated in the roster"
    )
    assert pip_owner in targets, (
        f"alice (Pip's owner) is connected → target should include her "
        f"id; got {targets}"
    )
    # GM excluded — player handles their own popup.
    # Look up GM id via the campaign roster — Tavik is GM-owned.
    tavik = roster["Brother Tavik Stonebrow"]
    gm_uid = tavik.get("owner_user_id")
    assert gm_uid is not None
    assert gm_uid not in targets, (
        f"alice is present → GM should NOT receive Pip's popup; "
        f"got targets={targets} (gm_uid={gm_uid})"
    )


async def test_oa_prompt_routes_to_gm_when_player_absent(
    gm_client, gm_ws, roster,
):
    """v2.99.59: alice does NOT have an open WS connection (note the
    fixture signature: no alice_ws requested). Krieger walks past
    Pip. Since alice is offline, the popup falls back to the GM so
    it doesn't vanish unhandled.
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    kr_tok = await _move_krieger_past_pip(gm_client, krieger, pip)
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    await asyncio.sleep(0.2)
    prompts = [
        m for m in gm_ws.buffered("reaction_prompt")
        if (m.get("data") or {}).get("watcher_char_id") == pip["id"]
    ]
    assert prompts, "expected reaction_prompt for Pip"
    targets = prompts[0]["data"].get("target_user_ids") or []
    tavik = roster["Brother Tavik Stonebrow"]
    gm_uid = tavik.get("owner_user_id")
    pip_owner = pip.get("owner_user_id")
    assert gm_uid in targets, (
        f"alice is absent → GM should receive Pip's popup as fallback; "
        f"got {targets}"
    )
    # Alice excluded — she's offline.
    assert pip_owner not in targets, (
        f"alice is offline → her id should NOT be in targets; "
        f"got {targets}"
    )


# ── v2.99.57 — plan-movement-oa-flow Phase 6: per-owner sub-queue ──


async def test_oa_parallel_prompts_when_watchers_have_different_owners(
    gm_client, gm_ws, roster,
):
    """v2.99.57: Krieger (GM-owned) walks past Pip (alice) AND
    Thalindra (bob). Both are PC watchers with different owners.
    Phase 6 partitions triggers by owner, so TWO reaction_prompts
    fire concurrently — one for each owner's queue.
    """
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]            # owned by alice
    thalindra = roster["Thalindra Moonwhisper"] # owned by bob
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(pip["name"], pip["id"], init=8),
        _make_combatant(thalindra["name"], thalindra["id"], init=6),
    ])
    # Pip 5 ft east, Thalindra 5 ft south of Krieger; moving Krieger
    # far away exits BOTH reaches.
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, pip["id"], 420.0, 350.0)
    await _place_token(gm_client, thalindra["id"], 350.0, 420.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 800.0, "y": 800.0, "oa_confirmed": True,
              "over_speed_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    await asyncio.sleep(0.2)

    prompts = _prompt_broadcasts(gm_ws)
    oa_prompts = [
        m for m in prompts
        if (m.get("data") or {}).get("trigger_event") in (
            "creature_exits_reach", "creature_enters_reach",
        )
    ]
    watcher_chars = sorted(
        (m.get("data") or {}).get("watcher_char_id") for m in oa_prompts
    )
    assert len(oa_prompts) == 2, (
        f"different-owner watchers should get parallel prompts; "
        f"got {len(oa_prompts)} with watcher_char_ids={watcher_chars}"
    )
    # Both PCs' char_ids surface.
    assert pip["id"] in watcher_chars, (
        f"expected Pip's prompt; got watcher_char_ids={watcher_chars}"
    )
    assert thalindra["id"] in watcher_chars, (
        f"expected Thalindra's prompt; got watcher_char_ids={watcher_chars}"
    )
    # Each prompt's next_triggers is EMPTY — each owner has only one
    # watcher in their group, so there's nothing to chain.
    for p in oa_prompts:
        # next_triggers lives in the prompt entry's context (server
        # side); on the broadcast it isn't directly exposed but the
        # absence of a 2nd prompt for the same owner after resolve
        # would prove parallelism. v1: just assert the broadcast had
        # the right shape.
        assert isinstance(p.get("data", {}).get("options"), list)


# ── v2.99.56 — plan-movement-oa-flow Phase 5: serial queue + picker + skip ──


def _prompt_broadcasts(gm_ws):
    return list(gm_ws.buffered("reaction_prompt"))


async def test_oa_serial_queue_emits_one_prompt_then_chains(
    gm_client, gm_ws, roster,
):
    """v2.99.56: when a move triggers TWO OAs (Krieger walks past
    both Tavik and Caelan), only ONE reaction_prompt fires on the
    /token/move call. After /use_reaction resolves the first, a
    SECOND reaction_prompt fires for the second watcher (the
    serial-queue chain).
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    caelan = roster["Sir Caelan Lightbringer"]
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        _make_combatant(tavik["name"], tavik["id"], init=8),
        _make_combatant(caelan["name"], caelan["id"], init=6),
    ])
    # Geometry: Krieger at (350, 350). Tavik 5 ft east. Caelan 5 ft
    # south. Moving Krieger to (700, 350) (5 cells east) exits the
    # reach of BOTH.
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    await _place_token(gm_client, tavik["id"], 420.0, 350.0)
    await _place_token(gm_client, caelan["id"], 350.0, 420.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Trigger the move (oa_confirmed=true to bypass the v2.99.55 409).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 800.0, "y": 800.0, "oa_confirmed": True,
              "over_speed_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # The move response carries BOTH triggers (the advisory list).
    triggers = data.get("opportunity_attack_triggers") or []
    assert len(triggers) >= 2, (
        f"expected 2 triggers (Tavik + Caelan); got {triggers}"
    )

    await asyncio.sleep(0.2)
    # Exactly ONE reaction_prompt fired so far — for the head.
    prompts = _prompt_broadcasts(gm_ws)
    oa_prompts = [
        m for m in prompts
        if (m.get("data") or {}).get("trigger_event") in (
            "creature_exits_reach", "creature_enters_reach",
        )
    ]
    assert len(oa_prompts) == 1, (
        f"expected exactly 1 OA reaction_prompt after the move "
        f"(serial queue); got {len(oa_prompts)}: "
        f"{[(m.get('data') or {}).get('watcher_name') for m in oa_prompts]}"
    )
    head_data = oa_prompts[0]["data"]
    # Resolving the head should fire a SECOND prompt for the other
    # watcher.
    prompt_id = head_data["prompt_id"]
    gm_ws.mark()
    resp2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "skip-oa",
            "watcher_char_id": head_data.get("watcher_char_id"),
        },
    )
    assert resp2.status_code == 200, resp2.text

    await asyncio.sleep(0.2)
    next_prompts = [
        m for m in gm_ws.buffered("reaction_prompt")
        if (m.get("data") or {}).get("trigger_event") in (
            "creature_exits_reach", "creature_enters_reach",
        )
    ]
    assert len(next_prompts) == 1, (
        f"resolving head should chain ONE next prompt for the tail; "
        f"got {len(next_prompts)}"
    )
    next_data = next_prompts[0]["data"]
    # The chained prompt's watcher must be DIFFERENT from the head's.
    assert next_data.get("watcher_combatant_id") != head_data.get(
        "watcher_combatant_id"
    ), (
        f"chained prompt should target the OTHER watcher; head was "
        f"{head_data.get('watcher_combatant_id')}, next was "
        f"{next_data.get('watcher_combatant_id')}"
    )


async def test_oa_prompt_includes_per_attack_picker_options(
    gm_client, gm_ws, roster,
):
    """v2.99.56: the OA prompt's options list includes one entry per
    melee attack on the watcher's sheet — keys of the form
    ``take-the-oa:{idx}`` with params carrying the attack metadata.
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
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    await asyncio.sleep(0.2)

    prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("watcher_char_id") == tavik["id"]
    ]
    assert prompts, "expected reaction_prompt for Tavik"
    options = prompts[0]["data"].get("options") or []
    keys = [o.get("key") for o in options]
    # v2.99.68 — the generic ``take-the-oa`` is a FALLBACK only,
    # emitted only when the per-attack picker is empty (no PC sheet
    # attacks / NPC template actions). Tavik has sheet attacks, so the
    # picker REPLACES the generic key here.
    assert "take-the-oa" not in keys, (
        f"generic take-the-oa should be replaced by the per-attack "
        f"picker when the watcher has attacks; got {keys}"
    )
    # At least one picker option for Tavik's mace / weapon attacks.
    picker_keys = [k for k in keys if k and k.startswith("take-the-oa:")]
    assert picker_keys, (
        f"expected at least one per-attack picker option; got {keys}"
    )
    # Skip option present.
    assert "skip-oa" in keys, (
        f"skip-oa option must be present; got {keys}"
    )
    # Picker entry params carry the attack name.
    picker_entry = next(
        (o for o in options if o.get("key") == picker_keys[0]), None,
    )
    assert picker_entry
    params = picker_entry.get("params") or {}
    assert isinstance(params.get("attack_index"), int)
    assert (params.get("attack_name") or "").strip(), (
        f"picker params should carry the attack name; got {params}"
    )


async def test_oa_use_reaction_skip_does_not_mark_reaction(
    gm_client, gm_ws, roster,
):
    """v2.99.56: POST /use_reaction with ``reaction_key=skip-oa``
    resolves the prompt but does NOT mark the watcher's reaction
    slot — the watcher can still react to a later trigger this
    round.

    v2.99.75 removed the "✋ OA skipped" audit broadcast ("no
    message needed to show that an OA has been skipped"), so this
    test no longer asserts a ``feature_used`` row — only that the
    reaction slot stays unmarked.
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
    assert prompts, "expected reaction_prompt for Tavik"
    prompt_id = prompts[0]["data"]["prompt_id"]

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "skip-oa",
            "watcher_char_id": tavik["id"],
        },
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    # Reaction slot NOT marked — no economy_update for Tavik's reaction.
    # (v2.99.75 removed the oa-skipped audit broadcast; the slot-unmarked
    # invariant is the behavior this test now guards.)
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == tavik["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
        and (m.get("data") or {}).get("used") is True
    ]
    assert not econ, (
        f"skip-oa must NOT mark the reaction slot; got {econ}"
    )


async def test_oa_use_reaction_attack_picker_marks_reaction_and_audits(
    gm_client, gm_ws, roster,
):
    """v2.99.56: POST /use_reaction with ``reaction_key=take-the-oa:0``
    (a per-attack picker key) marks the watcher's reaction slot.

    v2.99.75 removed the per-attack ``oa-attack-chosen`` audit
    broadcast — the v2.99.68 auto-chained /attack now lands the
    weapon-attack chat card (marked ``is_oa: True``) instead — so
    this test guards only the reaction-slot mark, not the audit row.
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
    assert prompts, "expected reaction_prompt for Tavik"
    prompt = prompts[0]["data"]
    prompt_id = prompt["prompt_id"]
    # Pick the first per-attack picker key.
    picker_keys = [
        o.get("key") for o in (prompt.get("options") or [])
        if (o.get("key") or "").startswith("take-the-oa:")
    ]
    assert picker_keys, "expected at least one picker option"
    chosen_key = picker_keys[0]

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": chosen_key,
            "watcher_char_id": tavik["id"],
        },
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    # Reaction slot marked.
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == tavik["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
        and (m.get("data") or {}).get("used") is True
    ]
    assert econ, "expected economy_update marking Tavik's reaction used"


# ── v2.99.55 — plan-movement-oa-flow Phase 4: oa_confirmed 409 gate ──


async def test_token_move_409_when_oa_triggers_without_confirmation(
    gm_client, gm_ws, roster,
):
    """v2.99.55: /token/move without ``oa_confirmed: true`` AND with
    triggers fires → 409 ``oa_confirmation_required`` + token
    position unchanged + no token_move broadcast. Defense-in-depth
    in case a malicious client races past the preview check.
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
    assert kr_tok
    await asyncio.sleep(0.15)
    gm_ws.mark()

    # Move to (750, 350) — exits Tavik's reach. Distinct coords
    # from the rest of the file so the replace_all `oa_confirmed`
    # sweep doesn't touch this call.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 750.0, "y": 350.0},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "oa_confirmation_required"
    assert body["would_trigger_oa"] is True
    triggers = [
        t for t in body.get("triggers", [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert triggers, (
        f"409 body should surface the Tavik trigger; got {body}"
    )

    # Token position must be unchanged.
    kr_tok_after = await _get_token_for_char(gm_client, krieger["id"])
    assert abs(kr_tok_after["x"] - 350.0) < 0.01, (
        f"409 must not move token; expected x=350.0, got {kr_tok_after['x']}"
    )

    # No token_move broadcast either — defense-in-depth means the
    # other clients shouldn't observe a phantom move.
    await asyncio.sleep(0.15)
    tm_msgs = [
        m for m in gm_ws.buffered("token_move")
        if (m.get("data") or {}).get("id") == kr_tok["id"]
    ]
    assert not tm_msgs, (
        f"409 path must not emit token_move; got {tm_msgs}"
    )


async def test_token_move_succeeds_with_oa_confirmed_true(
    gm_client, gm_ws, roster,
):
    """v2.99.55: POST /token/move with ``oa_confirmed: true`` AND
    triggers fires → 200 + token moves + triggers emit as today.
    Confirms the new flag opt-out from the 409 gate works.
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

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 750.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    triggers = [
        t for t in data.get("opportunity_attack_triggers") or []
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert triggers, (
        f"oa_confirmed=true should still surface the Tavik trigger; "
        f"got {data.get('opportunity_attack_triggers')}"
    )

    # Token moved.
    kr_tok_after = await _get_token_for_char(gm_client, krieger["id"])
    assert abs(kr_tok_after["x"] - 750.0) < 0.01, (
        f"oa_confirmed=true should commit the move; got x={kr_tok_after['x']}"
    )

    # Legacy feature_used advisory still fires.
    await asyncio.sleep(0.15)
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "opportunity-attack-trigger"
        and (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert fu, (
        f"oa_confirmed=true should still emit OA advisory broadcasts; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


# ── v2.99.54 — plan-movement-oa-flow Phase 3: preview_move endpoint ──


async def test_preview_move_returns_triggers_without_moving_token(
    gm_client, roster,
):
    """v2.99.54: POST /token/{id}/preview_move returns the trigger
    list a real /token/move would produce, AND leaves the token's
    position unchanged.
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
    assert kr_tok
    await asyncio.sleep(0.15)

    # Preview a move that would exit Tavik's 5 ft reach.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/preview_move",
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["would_trigger_oa"] is True
    assert data["distance_ft"] > 0
    triggers = [
        t for t in data.get("triggers", [])
        if t.get("watcher_char_id") == tavik["id"]
    ]
    assert triggers, (
        f"preview should surface a Tavik OA trigger; got {data['triggers']}"
    )
    assert triggers[0].get("trigger_type") == "exit"

    # Token position MUST be unchanged (preview is read-only).
    kr_tok_after = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok_after, "Krieger token still exists"
    assert abs(kr_tok_after["x"] - 350.0) < 0.01, (
        f"preview must not move token; expected x=350.0, got {kr_tok_after['x']}"
    )
    assert abs(kr_tok_after["y"] - 350.0) < 0.01, (
        f"preview must not move token; expected y=350.0, got {kr_tok_after['y']}"
    )


async def test_preview_move_honors_same_team_filter(
    gm_client, roster,
):
    """v2.99.54: preview respects the v2.99.52 same-team filter —
    same-team move returns would_trigger_oa=False even if the
    geometry would normally provoke an OA.
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
    tv_tok = await _get_token_for_char(gm_client, tavik["id"])
    await _set_team(gm_client, kr_tok["id"], "hero")
    await _set_team(gm_client, tv_tok["id"], "hero")
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/preview_move",
            json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["would_trigger_oa"] is False, (
            f"same-team preview should report no triggers; got {data}"
        )
        assert data["triggers"] == [], (
            f"same-team preview should return empty triggers; got {data['triggers']}"
        )
    finally:
        await _set_team(gm_client, kr_tok["id"], "neutral")
        await _set_team(gm_client, tv_tok["id"], "neutral")


# ── v2.100.0 — GM over-range advisory: preview_move speed fields ──


async def test_preview_move_reports_over_range_beyond_speed(
    gm_client, roster,
):
    """v2.100.0: preview_move returns token_speed_ft + over_range so
    the GM client can warn when a single drag exceeds the token's
    base walking speed. Read-only — the token must not move.
    """
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
    ])
    # 350 = 5 cells on the 70-px grid, so placement snaps to itself.
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok
    await asyncio.sleep(0.15)

    # 70-px grid → 5 ft/cell. 350→1400 x = 1050 px = 15 cells →
    # Chebyshev = 75 ft, comfortably beyond any normal walking speed
    # (30–60 ft), so over_range must be True regardless of Krieger's
    # exact projected speed.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/preview_move",
        json={"x": 1400.0, "y": 350.0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["token_speed_ft"] > 0, data
    assert data["distance_ft"] > data["token_speed_ft"], data
    assert data["over_range"] is True, data

    # Preview is read-only — position unchanged.
    kr_after = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_after and abs(kr_after["x"] - 350.0) < 0.01, (
        f"preview must not move token; got {kr_after}"
    )


async def test_preview_move_within_speed_not_over_range(
    gm_client, roster,
):
    """v2.100.0: a move shorter than the token's speed reports
    over_range=False so the GM client suppresses the advisory.
    """
    krieger = roster["Krieger Stonefist"]
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
    ])
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    assert kr_tok
    await asyncio.sleep(0.15)

    # 350→420 x = 70 px = 1 cell → 5 ft, well within any walking speed.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/preview_move",
        json={"x": 420.0, "y": 350.0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["token_speed_ft"] > 0, data
    assert data["distance_ft"] <= data["token_speed_ft"], data
    assert data["over_range"] is False, data


async def test_token_patch_team_field_persists_and_broadcasts(
    gm_client, gm_ws, roster,
):
    """v2.99.52: PATCH /token/{id} {team: "hero"} persists + the
    token_update broadcast carries team='hero' + the /tokens JSON
    projection surfaces it.
    """
    krieger = roster["Krieger Stonefist"]
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    gm_ws.mark()
    try:
        r = await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}",
            json={"team": "hero"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("team") == "hero"
        await asyncio.sleep(0.15)
        upd = [
            m for m in gm_ws.buffered("token_update")
            if (m.get("data") or {}).get("id") == kr_tok["id"]
        ]
        assert upd, "expected token_update broadcast after team PATCH"
        assert upd[-1]["data"].get("team") == "hero"
        # Echoed in /tokens GET.
        re_tok = await _get_token_for_char(gm_client, krieger["id"])
        assert re_tok.get("team") == "hero", (
            f"team field should surface in /tokens; got {re_tok}"
        )
        # Bad input clamps to neutral.
        r2 = await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}",
            json={"team": "rogues"},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json().get("team") == "neutral", (
            f"unknown team should clamp to neutral; got {r2.json()}"
        )
    finally:
        await _set_team(gm_client, kr_tok["id"], "neutral")


# ── v2.99.64 — multi-NPC-watcher chain regression ──


async def test_oa_chain_multi_npc_watchers_all_get_to_attack(
    gm_client, gm_ws, roster,
):
    """User report v2.99.63: moving a hero past TWO NPC watchers in
    one drag only fires the OA for ONE of them — the second never
    gets a popup. Multi-NPC partition collapses to a single GM owner
    queue with head + tail; the head emits a prompt, and the chain
    pop in /use_reaction is supposed to emit the tail's head when
    the first is resolved.

    Geometry: Krieger at (350, 350). Goon-A at (420, 350) (5 ft east),
    Goon-B at (350, 420) (5 ft south). Both NPCs seeded in the demo's
    exact shape — token_template_id + name (label) + no
    source_token_id, no char_id. Both default-owned by the GM.

    Expectations:
      - /token/move returns 2 OA triggers
      - exactly 1 reaction_prompt fires after the move (the GM-queue
        head)
      - resolving that prompt with skip-oa fires exactly 1 chained
        prompt for the OTHER NPC
    """
    krieger = roster["Krieger Stonefist"]

    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    for label, x, y in (("Goon-A", 420.0, 350.0), ("Goon-B", 350.0, 420.0)):
        tok_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/tokens",
            json={
                "token_template_id": bandit_tmpl["id"],
                "label": label,
                "x": x, "y": y,
                "color": "#c84a4a",
                "size": 1,
            },
        )
        assert tok_resp.status_code == 200, tok_resp.text

    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        {
            "id": "tok_oa_multi_npc_a",
            "char_id": None,
            "token_template_id": bandit_tmpl["id"],
            "name": "Goon-A",
            "initiative": 8,
            "hp_current": 11, "hp_max": 11,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
        {
            "id": "tok_oa_multi_npc_b",
            "char_id": None,
            "token_template_id": bandit_tmpl["id"],
            "name": "Goon-B",
            "initiative": 6,
            "hp_current": 11, "hp_max": 11,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    triggers = data.get("opportunity_attack_triggers") or []
    npc_trigs = [
        t for t in triggers
        if t.get("watcher_combatant_id") in (
            "tok_oa_multi_npc_a", "tok_oa_multi_npc_b",
        )
    ]
    assert len(npc_trigs) == 2, (
        f"expected 2 NPC triggers (Goon-A + Goon-B); got "
        f"{[t.get('watcher_combatant_id') for t in triggers]}"
    )

    await asyncio.sleep(0.2)

    oa_prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("trigger_event") in (
            "creature_exits_reach", "creature_enters_reach",
        )
    ]
    assert len(oa_prompts) == 1, (
        f"expected exactly 1 OA prompt after the move (serial "
        f"queue, both NPCs partition to GM); got {len(oa_prompts)}: "
        f"{[(m.get('data') or {}).get('watcher_combatant_id') for m in oa_prompts]}"
    )
    head_data = oa_prompts[0]["data"]
    head_wcid = head_data.get("watcher_combatant_id")
    assert head_wcid in ("tok_oa_multi_npc_a", "tok_oa_multi_npc_b"), (
        f"head prompt should target an NPC watcher; got {head_wcid}"
    )

    gm_ws.mark()
    resp2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": head_data["prompt_id"],
            "reaction_key": "skip-oa",
            "watcher_char_id": head_data.get("watcher_char_id"),
        },
    )
    assert resp2.status_code == 200, resp2.text

    await asyncio.sleep(0.2)
    next_prompts = [
        m for m in gm_ws.buffered("reaction_prompt")
        if (m.get("data") or {}).get("trigger_event") in (
            "creature_exits_reach", "creature_enters_reach",
        )
    ]
    assert len(next_prompts) == 1, (
        f"resolving the head should chain exactly 1 next prompt for "
        f"the other NPC; got {len(next_prompts)}"
    )
    next_wcid = next_prompts[0]["data"].get("watcher_combatant_id")
    assert next_wcid != head_wcid, (
        f"chained prompt should target the OTHER NPC; head was "
        f"{head_wcid}, next was {next_wcid}"
    )
    assert next_wcid in ("tok_oa_multi_npc_a", "tok_oa_multi_npc_b"), (
        f"chained prompt should target an NPC watcher; got {next_wcid}"
    )


async def test_oa_chain_multi_npc_take_the_oa_path(
    gm_client, gm_ws, roster,
):
    """v2.99.64 — same as the skip-oa variant above, but uses the
    take-the-oa reaction_key on the head. The user's "only one OA
    fires" report most likely came from clicking Take OA on the
    first popup (the GM's normal flow), not Skip. The chain pop
    should fire regardless of which reaction_key resolved the head.
    """
    krieger = roster["Krieger Stonefist"]

    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    for label, x, y in (("Goon-C", 420.0, 350.0), ("Goon-D", 350.0, 420.0)):
        tok_resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/tokens",
            json={
                "token_template_id": bandit_tmpl["id"],
                "label": label,
                "x": x, "y": y,
                "color": "#c84a4a",
                "size": 1,
            },
        )
        assert tok_resp.status_code == 200, tok_resp.text

    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=10),
        {
            "id": "tok_oa_multi_npc_c",
            "char_id": None,
            "token_template_id": bandit_tmpl["id"],
            "name": "Goon-C",
            "initiative": 8,
            "hp_current": 11, "hp_max": 11,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
        {
            "id": "tok_oa_multi_npc_d",
            "char_id": None,
            "token_template_id": bandit_tmpl["id"],
            "name": "Goon-D",
            "initiative": 6,
            "hp_current": 11, "hp_max": 11,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await _place_token(gm_client, krieger["id"], 350.0, 350.0)
    kr_tok = await _get_token_for_char(gm_client, krieger["id"])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{kr_tok['id']}/move",
        json={"x": 700.0, "y": 350.0, "oa_confirmed": True},
    )
    assert resp.status_code == 200, resp.text

    await asyncio.sleep(0.2)
    oa_prompts = [
        m for m in _prompt_broadcasts(gm_ws)
        if (m.get("data") or {}).get("trigger_event") in (
            "creature_exits_reach", "creature_enters_reach",
        )
        and (m.get("data") or {}).get("watcher_combatant_id") in (
            "tok_oa_multi_npc_c", "tok_oa_multi_npc_d",
        )
    ]
    assert len(oa_prompts) == 1, (
        f"expected 1 OA prompt for the head; got {len(oa_prompts)}"
    )
    head_data = oa_prompts[0]["data"]
    head_wcid = head_data.get("watcher_combatant_id")

    # Resolve by taking the OA. v2.99.68 gives multi-attack NPCs a
    # per-attack picker (``take-the-oa:{idx}``) and demotes the
    # generic ``take-the-oa`` to a fallback emitted only when no
    # picker options exist — so pick the picker key when present,
    # else the generic.
    _head_keys = [o.get("key") for o in (head_data.get("options") or [])]
    _take_key = next(
        (k for k in _head_keys if k and k.startswith("take-the-oa:")),
        "take-the-oa",
    )
    gm_ws.mark()
    resp2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": head_data["prompt_id"],
            "reaction_key": _take_key,
            "watcher_char_id": head_data.get("watcher_char_id"),
        },
    )
    assert resp2.status_code == 200, resp2.text

    await asyncio.sleep(0.2)
    next_prompts = [
        m for m in gm_ws.buffered("reaction_prompt")
        if (m.get("data") or {}).get("trigger_event") in (
            "creature_exits_reach", "creature_enters_reach",
        )
        and (m.get("data") or {}).get("watcher_combatant_id") in (
            "tok_oa_multi_npc_c", "tok_oa_multi_npc_d",
        )
    ]
    assert len(next_prompts) == 1, (
        f"resolving with take-the-oa should chain 1 next prompt; "
        f"got {len(next_prompts)}"
    )
    next_wcid = next_prompts[0]["data"].get("watcher_combatant_id")
    assert next_wcid != head_wcid, (
        f"chained prompt should target the OTHER NPC; head was "
        f"{head_wcid}, next was {next_wcid}"
    )
