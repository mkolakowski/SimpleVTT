"""v2.341.0 — magic-items: Mace of Smiting (RAW DMG p.179, rare, NO
attunement). The first on_nat_20 `effect: "damage"` item to use
`bonus_dice_vs`: a natural 20 deals +2d6 bludgeoning, or +4d6 vs a
construct (= base 2d6 + bonus 2d6, folded into the same broadcast). No
attunement → the rider fires on slug match alone.

Demo fixture: Brother Tavik Stonebrow (Life Cleric) carries it at
`attack_index 4`, equipped — a construct-smashing mace alongside his
Mace of Disruption. The +1/+3-vs-construct attack bonus + the
destroy-construct-at-≤25-HP clause are GM-narrated.

The construct-vs-humanoid damage distinction is verified statistically:
across a seed sweep, the construct nat-20 hp_dealt MAX must exceed 12
(impossible with only 2d6 — proves the +2d6 construct bonus fired),
while the humanoid hp_dealt values must ALL stay ≤ 12 (proves the bonus
does NOT leak to non-constructs).
"""
import re

import pytest_asyncio

from .conftest import CAMPAIGN_ID


TAVIK_MACE_OF_SMITING_ATTACK_IDX = 4
_SLAY_SOURCE = "item-mace-of-smiting-nat20"


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert r.status_code == 200, r.text


def _mkc(cid, char_id=None, name="X", creature_type="", ac=1, hp_max=200):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": ac,
        "buffs": [],
        "creature_type": creature_type,
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


def _smite_msgs(gm_ws):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == _SLAY_SOURCE
    ]


def _is_nat_20(data):
    breakdown = data.get("attack_breakdown") or ""
    m = re.search(r"\d*d20[^d=+ ]*=(\d+)", breakdown, re.IGNORECASE)
    return bool(m and int(m.group(1)) == 20)


@pytest_asyncio.fixture
async def tavik(roster):
    return roster["Brother Tavik Stonebrow"]


async def test_mace_of_smiting_bonus_vs_construct(gm_client, gm_ws, tavik):
    """v2.341.0: vs a construct, the nat-20 rider deals +4d6 (base 2d6 +
    construct bonus 2d6). Sweep seeds, collect every construct nat-20
    hp_dealt, and assert the MAX exceeds 12 — impossible with only 2d6, so
    it proves the +2d6 construct bonus fired."""
    target_hp = 200  # high so the smite never reduces it below the gate
    hp_values = []
    for seed in range(0, 300):
        await _seed_dice(gm_client, seed)
        tavik_cid = f"tok_smite_con_tavik_{tavik['id']}_{seed}"
        target_cid = f"tok_smite_con_target_{seed}"
        await _seed_battle(gm_client, [
            _mkc(tavik_cid, tavik["id"], name=tavik["name"]),
            _mkc(target_cid, None, name="Iron Golem",
                 creature_type="construct", hp_max=target_hp),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": TAVIK_MACE_OF_SMITING_ATTACK_IDX,
                "target_combatant_id": target_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if _is_nat_20(resp.json()):
            msgs = _smite_msgs(gm_ws)
            if msgs:
                hp = int((msgs[-1].get("data") or {}).get("hp_dealt") or 0)
                hp_values.append(hp)
                # Clear the buffer's relevance by tracking count instead —
                # but buffered() accumulates, so just collect the latest.

    assert hp_values, (
        "No Mace of Smiting nat-20 fired vs a construct across seeds 0..299."
    )
    # 4d6 → [4, 24]; 2d6 → [2, 12]. A value > 12 is only possible with 4d6,
    # proving the construct bonus fired.
    assert max(hp_values) > 12, (
        f"Construct nat-20 damage never exceeded 12 (max={max(hp_values)}) — "
        f"the +2d6 construct bonus_dice_vs may not be firing. Samples: "
        f"{hp_values}"
    )
    # Every value must still be within the 4d6 envelope [4, 24].
    assert all(4 <= v <= 24 for v in hp_values), hp_values

    await _seed_dice(gm_client, None)


async def test_mace_of_smiting_base_only_vs_humanoid(gm_client, gm_ws, tavik):
    """v2.341.0: vs a humanoid, only the base +2d6 fires — never the
    construct bonus. Sweep seeds, collect every humanoid nat-20 hp_dealt,
    and assert ALL are ≤ 12 (the 2d6 max) — so the construct bonus did NOT
    leak to a non-construct."""
    hp_values = []
    for seed in range(0, 300):
        await _seed_dice(gm_client, seed)
        tavik_cid = f"tok_smite_hum_tavik_{tavik['id']}_{seed}"
        target_cid = f"tok_smite_hum_target_{seed}"
        await _seed_battle(gm_client, [
            _mkc(tavik_cid, tavik["id"], name=tavik["name"]),
            _mkc(target_cid, None, name="Bandit",
                 creature_type="humanoid", hp_max=200),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": TAVIK_MACE_OF_SMITING_ATTACK_IDX,
                "target_combatant_id": target_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if _is_nat_20(resp.json()):
            msgs = _smite_msgs(gm_ws)
            if msgs:
                hp = int((msgs[-1].get("data") or {}).get("hp_dealt") or 0)
                hp_values.append(hp)

    assert hp_values, (
        "No Mace of Smiting nat-20 fired vs a humanoid across seeds 0..299."
    )
    # 2d6 → [2, 12]. NO value may exceed 12 (that would mean the construct
    # bonus leaked to a non-construct).
    assert all(2 <= v <= 12 for v in hp_values), (
        f"Humanoid nat-20 damage out of the 2d6 [2,12] envelope — the "
        f"construct bonus_dice_vs may be leaking. Samples: {hp_values}"
    )

    await _seed_dice(gm_client, None)
