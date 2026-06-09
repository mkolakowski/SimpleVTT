"""Phase 2a — auto-disadvantage / auto-advantage on attack rolls from
standard 5e condition buffs.

Attacker-side disadvantage: Blinded / Poisoned / Restrained / Frightened
/ Prone (PHB Appendix A). Target-side advantage: Blinded / Paralyzed /
Petrified / Restrained / Stunned / Unconscious. Plus the attacker-side
advantage half: Invisible.

Closes the docs/plans/advantage-disadvantage.md Phase 2 attacker- and
target-condition slice. Phase 3 (positional / melee-vs-ranged) still
deferred — Prone is intentionally not covered on the target side because
it only grants melee-advantage RAW.

Seeding strategy: standard-condition buffs are placed on the combatant's
`buffs` list at PUT /battle. The existing v2.97.30 mirror copies the
PC's combatant buffs back to `sheet._buffs_active`, so the attacker-side
helper picks them up without an extra `_install_buff` call.

Tests:
  - Attacker poisoned → 2d20kl1 + roll_state_applied =
    "disadvantage_attacker_poisoned".
  - Target restrained → 2d20kh1 + roll_state_applied =
    "advantage_target_restrained".
  - Attacker invisible → 2d20kh1 + roll_state_applied =
    "advantage_invisible".
  - Attacker poisoned + target restrained cancel per RAW PHB p.173 →
    single 1d20, roll_state_applied starts with "canceled_".
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


async def test_attacker_poisoned_imposes_disadvantage(
    gm_client, pip_full, roster,
):
    """Pip's combatant carries a `poisoned` buff (PUT /battle mirrors
    it into his sheet `_buffs_active`) → his attack roll drops to
    2d20kl1 with roll_state_applied = 'disadvantage_attacker_poisoned'."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[{"key": "poisoned", "name": "Poisoned"}],
        ),
        _mkc(tavik_cid, tavik["id"], name="Tavik"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": tavik_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" in (data.get("attack_breakdown") or ""), (
        f"Expected 2d20kl1; got {data.get('attack_breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "disadvantage_attacker_poisoned", (
        f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    )


async def test_target_restrained_grants_attacker_advantage(
    gm_client, pip_full, roster,
):
    """Tavik's combatant carries a `restrained` buff → Pip's attack roll
    becomes 2d20kh1 with roll_state_applied = 'advantage_target_restrained'."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip"),
        _mkc(
            tavik_cid, tavik["id"], name="Tavik",
            buffs=[{"key": "restrained", "name": "Restrained"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": tavik_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" in (data.get("attack_breakdown") or ""), (
        f"Expected 2d20kh1; got {data.get('attack_breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "advantage_target_restrained", (
        f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    )


async def test_attacker_invisible_grants_self_advantage(
    gm_client, pip_full, roster,
):
    """Pip's combatant carries an `invisible` buff → his attack roll
    becomes 2d20kh1 with roll_state_applied = 'advantage_invisible'."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[{"key": "invisible", "name": "Invisible"}],
        ),
        _mkc(tavik_cid, tavik["id"], name="Tavik"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": tavik_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" in (data.get("attack_breakdown") or ""), (
        f"Expected 2d20kh1; got {data.get('attack_breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "advantage_invisible", (
        f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    )


async def test_adv_and_dis_cancel_per_raw(
    gm_client, pip_full, roster,
):
    """RAW PHB p.173 — advantage + disadvantage cancel to a straight
    roll. Pip is poisoned (dis) AND Tavik is restrained (adv) → single
    1d20 + roll_state_applied starts with 'canceled_'."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[{"key": "poisoned", "name": "Poisoned"}],
        ),
        _mkc(
            tavik_cid, tavik["id"], name="Tavik",
            buffs=[{"key": "restrained", "name": "Restrained"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": tavik_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("attack_breakdown") or ""
    assert "2d20" not in breakdown, (
        f"Cancel should leave a single 1d20; got {breakdown!r}"
    )
    state = data.get("roll_state_applied") or ""
    assert state.startswith("canceled_"), (
        f"Expected canceled_*; got {state!r}"
    )
