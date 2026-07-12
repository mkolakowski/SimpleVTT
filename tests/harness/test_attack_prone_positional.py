"""Phase 3 (advantage-disadvantage plan) — positional prone edge on
attack rolls.

RAW PHB p.292: "An attack roll against a prone creature has advantage
if the attacker is within 5 feet of the creature. Otherwise, the attack
roll has disadvantage." Distance-based, not melee/ranged-based.

Long deferred as "blocked on Maps 2.0"; ships in v2.1001.0 riding the
existing substrate (`_combatant_token` + `_distance_ft_between_points`
— the same primitives the aura range gates and Unwavering Mark use).
The new `_target_prone_positional_edge` helper fires only when the
target combatant carries a `prone` buff AND both sides resolve to a
token on the active gridded map; otherwise it returns None and the
attack behaves exactly as before (off-grid prone stays GM-adjudicated).

Seeding strategy mirrors test_attack_condition_adv_dis.py (condition
buffs on the combatant at PUT /battle) + test_unwavering_mark.py
(token placement via POST /character/{id}/place-token in the proven
(700, 700) demo-map region; 70 px grid cell = 5 ft).

Tests:
  - Target prone + attacker 1 cell away (5 ft) → 2d20kh1 +
    roll_state_applied = "advantage_target_prone_within_5ft".
  - Target prone + attacker 4 cells away (20 ft) → 2d20kl1 +
    roll_state_applied = "disadvantage_target_prone_beyond_5ft".
  - Target prone with NO tokens on the map → straight 1d20, no edge
    (the None fallback — the error-path contract).
  - Attacker prone + target prone within 5 ft → canceled per RAW PHB
    p.173 (attacker_prone disadvantage vs target-prone advantage).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def pip_full(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    return pip


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


def _mkc(cid, char_id=None, hp_cur=30, hp_max=30, name="X", buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _delete_token(gm_client, char_id):
    await gm_client.delete(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/token",
    )


async def _attack(gm_client, attacker_char_id, target_cid):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": attacker_char_id,
            "attack_index": 0,
            "target_combatant_id": target_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_prone_target_within_5ft_grants_advantage(
    gm_client, pip_full, roster,
):
    """Tavik prone, Pip's token one grid cell away (70 px = 5 ft) →
    advantage: 2d20kh1 + 'advantage_target_prone_within_5ft'."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip"),
        _mkc(
            tavik_cid, tavik["id"], name="Tavik",
            buffs=[{"key": "prone", "name": "Prone"}],
        ),
    ])
    await _place_token(gm_client, pip["id"], 700.0, 700.0)
    await _place_token(gm_client, tavik["id"], 770.0, 700.0)
    try:
        data = await _attack(gm_client, pip["id"], tavik_cid)
        assert "2d20kh1" in (data.get("attack_breakdown") or ""), (
            f"Expected 2d20kh1; got {data.get('attack_breakdown')!r}"
        )
        assert data.get("roll_state_applied") == (
            "advantage_target_prone_within_5ft"
        ), f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    finally:
        await _delete_token(gm_client, pip["id"])
        await _delete_token(gm_client, tavik["id"])


async def test_prone_target_beyond_5ft_imposes_disadvantage(
    gm_client, pip_full, roster,
):
    """Tavik prone, Pip's token four grid cells away (280 px = 20 ft) →
    disadvantage: 2d20kl1 + 'disadvantage_target_prone_beyond_5ft'."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip"),
        _mkc(
            tavik_cid, tavik["id"], name="Tavik",
            buffs=[{"key": "prone", "name": "Prone"}],
        ),
    ])
    await _place_token(gm_client, pip["id"], 700.0, 700.0)
    await _place_token(gm_client, tavik["id"], 980.0, 700.0)
    try:
        data = await _attack(gm_client, pip["id"], tavik_cid)
        assert "2d20kl1" in (data.get("attack_breakdown") or ""), (
            f"Expected 2d20kl1; got {data.get('attack_breakdown')!r}"
        )
        assert data.get("roll_state_applied") == (
            "disadvantage_target_prone_beyond_5ft"
        ), f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    finally:
        await _delete_token(gm_client, pip["id"])
        await _delete_token(gm_client, tavik["id"])


async def test_prone_target_offgrid_no_edge(
    gm_client, pip_full, roster,
):
    """No tokens on the map → the positional edge can't resolve and the
    prone target imposes NO adv/dis (the pre-Phase-3 GM-adjudicated
    fallback): single 1d20, no roll_state_applied."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _delete_token(gm_client, pip["id"])
    await _delete_token(gm_client, tavik["id"])
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip"),
        _mkc(
            tavik_cid, tavik["id"], name="Tavik",
            buffs=[{"key": "prone", "name": "Prone"}],
        ),
    ])
    data = await _attack(gm_client, pip["id"], tavik_cid)
    breakdown = data.get("attack_breakdown") or ""
    assert "2d20" not in breakdown, (
        f"Off-grid prone must stay a straight 1d20; got {breakdown!r}"
    )
    assert not data.get("roll_state_applied"), (
        f"Expected no roll_state; got {data.get('roll_state_applied')!r}"
    )


async def test_prone_adv_cancels_attacker_prone_dis(
    gm_client, pip_full, roster,
):
    """Pip is ALSO prone (attacker-side disadvantage, Phase 2a) while
    adjacent to prone Tavik (target-side advantage, Phase 3) → RAW PHB
    p.173 cancel: single 1d20 + roll_state 'canceled_*'."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[{"key": "prone", "name": "Prone"}],
        ),
        _mkc(
            tavik_cid, tavik["id"], name="Tavik",
            buffs=[{"key": "prone", "name": "Prone"}],
        ),
    ])
    await _place_token(gm_client, pip["id"], 700.0, 700.0)
    await _place_token(gm_client, tavik["id"], 770.0, 700.0)
    try:
        data = await _attack(gm_client, pip["id"], tavik_cid)
        breakdown = data.get("attack_breakdown") or ""
        assert "2d20" not in breakdown, (
            f"Cancel should leave a single 1d20; got {breakdown!r}"
        )
        state = data.get("roll_state_applied") or ""
        assert state.startswith("canceled_"), (
            f"Expected canceled_*; got {state!r}"
        )
    finally:
        await _delete_token(gm_client, pip["id"])
        await _delete_token(gm_client, tavik["id"])
        # Clear the prone buffs so a later suite attacking with Pip in
        # the still-active battle doesn't inherit attacker-prone
        # disadvantage (Phase 2a) from this test's seed.
        await _seed_battle(gm_client, [
            _mkc(pip_cid, pip["id"], name="Pip"),
            _mkc(tavik_cid, tavik["id"], name="Tavik"),
        ])
