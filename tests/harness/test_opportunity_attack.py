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
