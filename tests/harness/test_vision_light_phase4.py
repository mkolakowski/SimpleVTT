"""v2.709.0 — Vision & Light Phase 4 (docs/plans/vision-and-light.md).

Hide / Stealth & the unseen-attacker advantage:
  - `POST /api/campaign/{cid}/hide` {combatant_id, stealth_score?} installs a
    `hidden` buff carrying the Stealth score (rolled if not given);
  - `_visibility_between` treats a hidden creature as **unseen** to any
    observer whose passive Perception is lower (truesight/blindsight defeat
    hiding); so attacking from hidden gets advantage via the Phase-2 wiring;
  - attacking **reveals** the hidden attacker (the `hidden` buff is cleared).

Bright map throughout, so hiding is the only thing driving the verdict.
Attacker Pip, target Garrik, 5 ft apart, in an active battle.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

PIP_TOK = "tok_v4_pip"
GAR_TOK = "tok_v4_gar"
_TS = [{"key": "ts", "name": "Truesight", "effects": {"truesight_ft": 60}}]


def _cb(tok_id, char, init, buffs=None):
    return {"id": tok_id, "char_id": char["id"], "name": char["name"],
            "initiative": init, "hp_current": 60, "hp_max": 60,
            "buffs": buffs or [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed(gm_client, pip, garrik, pip_buffs=None):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_cb(PIP_TOK, pip, 20, pip_buffs),
                             _cb(GAR_TOK, garrik, 8)],
              "turn_index": 0, "round": 1, "active": True})


async def _hide(gm_client, combatant_id, stealth_score):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/hide",
        json={"combatant_id": combatant_id, "stealth_score": stealth_score})
    return r


async def _visibility(gm_client, attacker, target):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/visibility",
        params={"attacker_combatant_id": attacker,
                "target_combatant_id": target})
    assert r.status_code == 200, r.text
    return r.json()


async def _attack(gm_client, pip):
    a = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0,
              "target_combatant_id": GAR_TOK, "override": True})
    assert a.status_code == 200, a.text
    return a.json().get("roll_state_applied") or ""


@pytest_asyncio.fixture
async def scene(gm_client, roster):
    pip, garrik = roster["Pip Quickfingers"], roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"})
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/place-token",
        json={"x": 350.0, "y": 350.0})
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/place-token",
        json={"x": 420.0, "y": 350.0})
    try:
        yield {"pip": pip, "garrik": garrik}
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False})


async def test_hide_installs_score(gm_client, scene):
    await _seed(gm_client, scene["pip"], scene["garrik"])
    r = await _hide(gm_client, GAR_TOK, 25)
    assert r.status_code == 200, r.text
    assert r.json()["stealth_score"] == 25


async def test_hidden_target_unseen_to_low_perception(gm_client, scene):
    """A hidden target (Stealth 99) is unseen to Pip (passive Perception well
    below 99)."""
    await _seed(gm_client, scene["pip"], scene["garrik"])
    await _hide(gm_client, GAR_TOK, 99)
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["visibility"] == "unseen", v
    assert v.get("hidden") is True, v


async def test_hidden_target_seen_when_perception_beats_stealth(gm_client, scene):
    """A poor hide (Stealth 1) is beaten by Pip's passive Perception → seen."""
    await _seed(gm_client, scene["pip"], scene["garrik"])
    await _hide(gm_client, GAR_TOK, 1)
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["visibility"] == "seen", v


async def test_truesight_defeats_hide(gm_client, scene):
    """Truesight sees a hidden creature regardless of Stealth."""
    await _seed(gm_client, scene["pip"], scene["garrik"], pip_buffs=list(_TS))
    await _hide(gm_client, GAR_TOK, 99)
    v = await _visibility(gm_client, PIP_TOK, GAR_TOK)
    assert v["visibility"] == "seen", v


async def test_hidden_attacker_advantage_then_revealed(gm_client, scene):
    """A hidden Pip (Stealth 99) attacks Garrik → advantage_unseen_attacker;
    the attack reveals Pip, so a second swing has no unseen edge."""
    await _seed(gm_client, scene["pip"], scene["garrik"])
    await _hide(gm_client, PIP_TOK, 99)
    first = await _attack(gm_client, scene["pip"])
    assert first == "advantage_unseen_attacker", first
    # Revealed: Garrik can now see Pip again.
    v = await _visibility(gm_client, GAR_TOK, PIP_TOK)
    assert v["visibility"] == "seen", v
    second = await _attack(gm_client, scene["pip"])
    assert "unseen_attacker" not in second, second


async def test_hide_unknown_combatant_404(gm_client, scene):
    await _seed(gm_client, scene["pip"], scene["garrik"])
    r = await _hide(gm_client, "tok_does_not_exist", 20)
    assert r.status_code == 404, r.text


async def test_hide_missing_combatant_id_400(gm_client, scene):
    await _seed(gm_client, scene["pip"], scene["garrik"])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/hide", json={"stealth_score": 20})
    assert r.status_code == 400, r.text


async def test_hide_non_gm_403(alice_client, gm_client, scene):
    await _seed(gm_client, scene["pip"], scene["garrik"])
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/hide",
        json={"combatant_id": GAR_TOK, "stealth_score": 20})
    assert r.status_code == 403, r.text
