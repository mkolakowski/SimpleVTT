"""v2.158.53 — Vengeance Paladin: Vow of Enmity Phase 2 read site.

v2.99.246 shipped `/use_vow_of_enmity`, which installs a
`vow-of-enmity-active` buff on the caster's combatant carrying
`effects.attack_advantage_vs_target_combatant_id` (the marked
target's combatant id). RAW PHB p.88: "you gain advantage on
attack rolls against the creature for 1 minute." But nothing read
that flag — the advantage was announce-only / GM-tracked.

This wires the read into `/attack`: a new helper
`_attacker_has_vow_of_enmity_vs_target` walks the attacker's
combatant buffs and, when `vow-of-enmity-active` names the current
target's combatant id, folds advantage onto the d20 attack roll
(label `advantage_vow_of_enmity`). The match is per-target, so the
vow grants advantage ONLY against the marked creature.

Seeding strategy mirrors `test_attack_condition_adv_dis.py`: the
buff is placed directly on the attacker's combatant `buffs` list at
PUT /battle (the resolver reads hub combatant buffs, no
`_install_buff` needed).

Tests:
  - Attacker carries vow vs the target → 2d20kh1 +
    roll_state_applied = "advantage_vow_of_enmity".
  - Attacker carries vow vs a DIFFERENT combatant → straight 1d20,
    no advantage (per-target match guard).
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


def _voe_buff(target_combatant_id):
    return {
        "key": "vow-of-enmity-active",
        "name": "Vow of Enmity",
        "icon": "🩸",
        "effects": {
            "attack_advantage_vs_target_combatant_id": target_combatant_id,
        },
    }


async def test_vow_of_enmity_grants_advantage_vs_marked_target(
    gm_client, pip_full, roster,
):
    """Pip's combatant carries `vow-of-enmity-active` naming Tavik's
    combatant id → his attack roll vs Tavik becomes 2d20kh1 with
    roll_state_applied = 'advantage_vow_of_enmity'."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip", buffs=[_voe_buff(tavik_cid)]),
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
    assert data.get("roll_state_applied") == "advantage_vow_of_enmity", (
        f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    )


async def test_vow_of_enmity_no_advantage_vs_other_target(
    gm_client, pip_full, roster,
):
    """Per-target guard: Pip's vow names a DIFFERENT combatant, so an
    attack vs Tavik gets NO Vow-of-Enmity advantage → straight 1d20."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip",
             buffs=[_voe_buff("tok_some_other_target")]),
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
    assert "2d20" not in (data.get("attack_breakdown") or ""), (
        f"Vow vs another target should not grant advantage; "
        f"got {data.get('attack_breakdown')!r}"
    )
    assert data.get("roll_state_applied") != "advantage_vow_of_enmity", (
        f"unexpected vow advantage; got {data.get('roll_state_applied')!r}"
    )
