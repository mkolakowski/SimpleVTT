"""Phase 2b — auto-disadvantage on saves + checks from standard 5e
condition buffs.

RAW PHB Appendix A:
  - Poisoned: disadvantage on ability checks.
  - Frightened: disadvantage on ability checks (while source visible
    RAW; v1 simplifies to always).
  - Restrained: disadvantage on DEX saves.

Phase 2a (v2.152.0) covered the attack-roll surface. Phase 2b covers
the generic ``/api/campaign/{cid}/roll`` endpoint that backs ability
checks + saves + skill rolls. The new ``_roll_condition_disadvantage``
helper reads ``stat_key`` / ``stat_ability`` to gate each condition
to its RAW-correct surface; generic untyped rolls don't trigger.

Seeding strategy: standard-condition buffs go on the PC's combatant
``buffs`` list via PUT /battle. The v2.97.30 mirror copies the PC's
combatant buffs back to ``sheet._buffs_active``, so the helper picks
them up without a separate ``_install_buff`` call.

Tests:
  - Poisoned attacker → ability check (str_check) → 2d20kl1 +
    roll_state_applied = "auto_disadvantage_poisoned".
  - Frightened attacker → ability check (perception) → 2d20kl1 +
    roll_state_applied = "auto_disadvantage_frightened".
  - Restrained attacker → DEX save → 2d20kl1 +
    roll_state_applied = "auto_disadvantage_restrained".
  - Restrained attacker → STR save (control) → 1d20, no disadvantage
    label.
  - Poisoned attacker → save (control) → 1d20, no disadvantage label
    (poisoned only disadvantages CHECKS, not saves).
  - Manual ``1d20a`` advantage + Poisoned check → cancel per RAW
    PHB p.173 → single 1d20 + roll_state_applied starts with
    "canceled_".
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
        "economy": {
            "action": False, "bonus": False,
            "reaction": False, "movement": 0,
        },
    }


async def test_poisoned_check_imposes_disadvantage(
    gm_client, pip_full,
):
    """Pip is poisoned → STR check rolls 2d20kl1 +
    roll_state_applied = 'auto_disadvantage_poisoned'."""
    pip = pip_full
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[{"key": "poisoned", "name": "Poisoned"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": pip["id"],
            "stat_key": "str_check",
            "stat_ability": "STR",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" in (data.get("breakdown") or ""), (
        f"Expected 2d20kl1; got breakdown={data.get('breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "auto_disadvantage_poisoned", (
        f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    )


async def test_frightened_check_imposes_disadvantage(
    gm_client, pip_full,
):
    """Pip is frightened → Perception check rolls 2d20kl1 +
    roll_state_applied = 'auto_disadvantage_frightened'."""
    pip = pip_full
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[{"key": "frightened", "name": "Frightened"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": pip["id"],
            "stat_key": "Perception",
            "stat_ability": "WIS",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") == "auto_disadvantage_frightened"


async def test_restrained_dex_save_imposes_disadvantage(
    gm_client, pip_full,
):
    """Pip is restrained → DEX save rolls 2d20kl1 +
    roll_state_applied = 'auto_disadvantage_restrained'."""
    pip = pip_full
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[{"key": "restrained", "name": "Restrained"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": pip["id"],
            "stat_key": "dex_save",
            "stat_ability": "DEX",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") == "auto_disadvantage_restrained"


async def test_restrained_str_save_no_disadvantage(
    gm_client, pip_full,
):
    """Control: Restrained gives disadvantage on DEX saves only, NOT
    on STR saves. Pip is restrained + rolls a STR save → no
    disadvantage applied."""
    pip = pip_full
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[{"key": "restrained", "name": "Restrained"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": pip["id"],
            "stat_key": "str_save",
            "stat_ability": "STR",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" not in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") in (None, "")


async def test_poisoned_save_no_disadvantage(
    gm_client, pip_full,
):
    """Control: Poisoned gives disadvantage on CHECKS only, NOT saves.
    Pip is poisoned + rolls a WIS save → no disadvantage applied."""
    pip = pip_full
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[{"key": "poisoned", "name": "Poisoned"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": pip["id"],
            "stat_key": "wis_save",
            "stat_ability": "WIS",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kl1" not in (data.get("breakdown") or "")
    assert data.get("roll_state_applied") in (None, "")


async def test_manual_advantage_vs_condition_disadvantage_cancels(
    gm_client, pip_full,
):
    """RAW PHB p.173 — manual ``1d20a`` (advantage) + Poisoned check
    cancel to a straight 1d20 with a 'canceled_*' roll_state_applied
    label."""
    pip = pip_full
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[{"key": "poisoned", "name": "Poisoned"}],
        ),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20a",
            "character_id": pip["id"],
            "stat_key": "str_check",
            "stat_ability": "STR",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("breakdown") or ""
    assert "2d20" not in breakdown, (
        f"Cancel should leave a single 1d20; got {breakdown!r}"
    )
    state = data.get("roll_state_applied") or ""
    assert state.startswith("canceled_"), (
        f"Expected canceled_*; got {state!r}"
    )
