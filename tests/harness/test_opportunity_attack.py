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


FIREBALL_INDEX = 7  # Thalindra's spell list — DEX save


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
    """
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}/move",
        json={"x": float(x), "y": float(y)},
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
        json={"x": 700.0, "y": 350.0},
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
        json={"x": 700.0, "y": 350.0},
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
        json={"x": 280.0, "y": 350.0},
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
        json={"x": 560.0, "y": 350.0},
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
        json={"x": 560.0, "y": 350.0},
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
        json={"x": 560.0, "y": 350.0},
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
        json={"x": 490.0, "y": 350.0},
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
        json={"x": 490.0, "y": 350.0},
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
            json={"x": 700.0, "y": 350.0},
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
            json={"x": 700.0, "y": 350.0},
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
            json={"x": 700.0, "y": 350.0},
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
