"""v2.158.50 — Devil's Sight read site (Phase 2).

The Warlock invocation Devil's Sight (PHB p.110) lets its owner see
normally in magical and nonmagical darkness out to 120 ft. The
`/use_devils_sight` endpoint (v2.158.14) installs a permanent
`devils-sight-active` buff carrying `devils_sight_range_ft: 120`;
until now that buff was announce-only.

This commit wires the read site into the attack-roll disadvantage
adjudication. `_attacker_has_condition_disadvantage` now skips a
`blinded` condition that is *darkness-sourced*
(`effects.from_darkness: True`, or a `source_spell`/`source` naming
darkness) when the attacker carries `devils-sight-active`. Blindness
from any other source (Blindness/Deafness, a blinding gaze) and every
other disadvantage condition are unaffected.

Seeding strategy mirrors test_attack_condition_adv_dis.py — condition
buffs go on the combatant's `buffs` list at PUT /battle; the v2.97.30
mirror copies them into the PC's `sheet._buffs_active`, so the
attacker-side helper picks them up without an extra install call.

Tests:
  - Darkness-blinded + Devil's Sight → disadvantage negated (straight
    1d20, roll_state_applied != "disadvantage_attacker_blinded").
  - Darkness-blinded, NO Devil's Sight (control) → 2d20kl1 +
    roll_state_applied == "disadvantage_attacker_blinded".
  - Non-darkness blinded + Devil's Sight (guard) → disadvantage STILL
    applies; Devil's Sight does not cure blindness from other sources.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


_DEVILS_SIGHT_BUFF = {
    "key": "devils-sight-active",
    "name": "Devil's Sight",
    "effects": {
        "devils_sight_range_ft": 120,
        "devils_sight_through_magical_darkness": True,
    },
}


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


async def _attack(gm_client, attacker_id, target_cid):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": attacker_id,
            "attack_index": 0,
            "target_combatant_id": target_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_devils_sight_negates_darkness_blinded_disadvantage(
    gm_client, pip_full, roster,
):
    """Pip is `blinded` by darkness (`effects.from_darkness: True`) AND
    carries `devils-sight-active` → the darkness blindness is ignored,
    so his attack roll stays a straight 1d20 and roll_state_applied is
    NOT 'disadvantage_attacker_blinded'."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[
                {
                    "key": "blinded",
                    "name": "Blinded (Darkness)",
                    "effects": {"from_darkness": True},
                },
                dict(_DEVILS_SIGHT_BUFF),
            ],
        ),
        _mkc(tavik_cid, tavik["id"], name="Tavik"),
    ])
    data = await _attack(gm_client, pip["id"], tavik_cid)
    breakdown = data.get("attack_breakdown") or ""
    assert "2d20kl1" not in breakdown, (
        f"Devil's Sight should cancel darkness-blind disadvantage; "
        f"got {breakdown!r}"
    )
    assert data.get("roll_state_applied") != "disadvantage_attacker_blinded", (
        f"roll_state_applied should not flag blinded disadvantage; "
        f"got {data.get('roll_state_applied')!r}"
    )


async def test_darkness_blinded_without_devils_sight_imposes_disadvantage(
    gm_client, pip_full, roster,
):
    """Control — Pip is darkness-`blinded` but has NO Devil's Sight →
    the disadvantage applies normally: 2d20kl1 + roll_state_applied ==
    'disadvantage_attacker_blinded'.

    v2.159.25 — Pip's demo seed now includes Goggles of Night (equipped
    by default) which compose with `_pc_sees_in_darkness` the same way
    Devil's Sight does. To preserve this control's "no sees-in-darkness
    source" semantics, unequip the Goggles first; restore on teardown."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    # v2.159.25 — toggle Goggles off so the darkness-blinded
    # disadvantage actually fires.
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = list(sheet.get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    for i, it in enumerate(inv):
        if isinstance(it, dict) and it.get("_slug") == "goggles-of-night":
            inv[i] = {**it, "equipped": False}
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"inventory": inv},
    )
    try:
        pip_cid = f"tok_{pip['id']}"
        tavik_cid = f"tok_{tavik['id']}"
        await _seed_battle(gm_client, [
            _mkc(
                pip_cid, pip["id"], name="Pip",
                buffs=[{
                    "key": "blinded",
                    "name": "Blinded (Darkness)",
                    "effects": {"from_darkness": True},
                }],
            ),
            _mkc(tavik_cid, tavik["id"], name="Tavik"),
        ])
        data = await _attack(gm_client, pip["id"], tavik_cid)
        assert "2d20kl1" in (data.get("attack_breakdown") or ""), (
            f"Expected 2d20kl1 without Devil's Sight; "
            f"got {data.get('attack_breakdown')!r}"
        )
        assert data.get("roll_state_applied") == "disadvantage_attacker_blinded", (
            f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_devils_sight_does_not_cure_non_darkness_blindness(
    gm_client, pip_full, roster,
):
    """Guard — Pip carries Devil's Sight but his `blinded` condition is
    NOT darkness-sourced (no `from_darkness` marker, e.g. a
    Blindness/Deafness spell) → the disadvantage STILL applies. Devil's
    Sight only negates the inability to see in darkness."""
    pip = pip_full
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_{pip['id']}"
    tavik_cid = f"tok_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(
            pip_cid, pip["id"], name="Pip",
            buffs=[
                {"key": "blinded", "name": "Blinded (Spell)"},
                dict(_DEVILS_SIGHT_BUFF),
            ],
        ),
        _mkc(tavik_cid, tavik["id"], name="Tavik"),
    ])
    data = await _attack(gm_client, pip["id"], tavik_cid)
    assert "2d20kl1" in (data.get("attack_breakdown") or ""), (
        f"Non-darkness blindness should still impose disadvantage; "
        f"got {data.get('attack_breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "disadvantage_attacker_blinded", (
        f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    )
