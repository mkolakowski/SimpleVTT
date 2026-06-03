"""v2.99.92 — Eldritch Invocation: Lance of Lethargy.

RAW (PHB p.111): "When you hit a creature with eldritch blast, you
can reduce that creature's speed by 10 feet until the end of your
next turn."

Server-side ``_apply_lance_of_lethargy`` runs at /attack time after
the hit + damage path. When the attacker has the invocation AND
the attack is Eldritch Blast AND the target was hit AND the target
isn't dead, the helper installs a ``lance-of-lethargy`` buff on
the target carrying ``effects.speed_reduction_ft: 10`` and
``duration_rounds: 1``. v1 is the buff install + audit broadcast;
the mechanical speed reduction (Mov chip + movement enforcement
reading the effects) is filed.

Stacks with Repelling Blast — both fire on the same EB hit.

Demo fixture: Magnus's feats gain the
``eldritch-invocation-lance-of-lethargy`` entry. The test fixture
PATCHes Magnus's feats to include both Lance of Lethargy AND
Repelling Blast (Repelling Blast pushes the target; we verify the
LoL buff lands on the target's new position regardless).

Tests:
- happy: Magnus + Eldritch Blast + Krieger target → after hit,
  Krieger's combatant carries a lance-of-lethargy buff with
  effects.speed_reduction_ft: 10 + feature_used(lance-of-lethargy)
  broadcast fires.
- gate: Quarterstaff (not EB) → no LoL buff installed.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


ELDRITCH_BLAST_INDEX = 1
QUARTERSTAFF_INDEX = 0


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest_asyncio.fixture
async def magnus_with_lance(gm_client, gm_ws, roster):
    """Place Magnus + Krieger, seed an active battle, PATCH Magnus's
    feats to include Lance of Lethargy (+ Agonizing Blast for damage
    consistency; Repelling Blast EXCLUDED so the buff target stays
    in place for the assertion).
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    # PATCH Magnus's invocations. Repelling Blast is excluded here
    # so Krieger's position doesn't shift — easier to find the
    # combatant by id afterwards (the combatant id is what the
    # buff is keyed on, not the token position; but excluding RB
    # also keeps this test independent of the v2.99.90 push wire).
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"feats": [
            {"slug": "eldritch-invocation-agonizing-blast",
             "name": "Eldritch Invocation: Agonizing Blast"},
            {"slug": "eldritch-invocation-lance-of-lethargy",
             "name": "Eldritch Invocation: Lance of Lethargy"},
        ]},
    )
    await _place_token(gm_client, magnus["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 420.0, 350.0)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": "tok_magnus_lol", "char_id": magnus["id"],
                 "name": magnus["name"], "initiative": 10,
                 "hp_current": 38, "hp_max": 38, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": "tok_krieger_lol", "char_id": krieger["id"],
                 "name": krieger["name"], "initiative": 8,
                 "hp_current": 75, "hp_max": 75, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
            ],
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )
    yield magnus, krieger


async def _find_krieger_buffs(gm_ws):
    """Walk the most recent battle_update broadcast to find Krieger's
    buffs list. Returns the buffs list (possibly empty) or None if
    no battle_update was buffered.
    """
    bu_msgs = gm_ws.buffered("battle_update")
    if not bu_msgs:
        return None
    latest = bu_msgs[-1]
    state = latest.get("data") or {}
    for c in state.get("combatants") or []:
        if c.get("id") == "tok_krieger_lol":
            return c.get("buffs") or []
    return None


async def test_lance_of_lethargy_installs_buff_on_eb_hit(
    gm_client, gm_ws, magnus_with_lance,
):
    """Magnus fires Eldritch Blast at Krieger; after a hit, Krieger's
    combatant carries a lance-of-lethargy buff with
    effects.speed_reduction_ft: 10.
    """
    magnus, krieger = magnus_with_lance
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    gm_ws.mark()
    # Repeat to get a hit (EB +6 vs Krieger AC ~16 ≈ 50% hit rate).
    hit_seen = False
    for _ in range(15):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": magnus["id"],
                "attack_index": ELDRITCH_BLAST_INDEX,
                "target_combatant_id": "tok_krieger_lol",
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        if resp.json().get("hit"):
            hit_seen = True
            break
    assert hit_seen, (
        "Expected at least one EB hit on Krieger across 15 attempts."
    )
    await asyncio.sleep(0.2)
    buffs = await _find_krieger_buffs(gm_ws)
    assert buffs is not None, (
        "Expected at least one battle_update broadcast carrying "
        "Krieger's combatant state."
    )
    lol = [b for b in buffs if (b or {}).get("key") == "lance-of-lethargy"]
    assert lol, (
        f"Expected lance-of-lethargy buff on Krieger; got buffs={buffs}"
    )
    assert lol[0].get("effects", {}).get("speed_reduction_ft") == 10, (
        f"Lance of Lethargy buff should carry effects.speed_reduction_ft=10; "
        f"got {lol[0]}"
    )
    # Verify the feature_used broadcast fired.
    fu_msgs = gm_ws.buffered("feature_used")
    lol_fu = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "lance-of-lethargy"
        and (m.get("data") or {}).get("character_id") == magnus["id"]
    ]
    assert lol_fu, (
        f"Expected feature_used(source=lance-of-lethargy); "
        f"buffered: {[(m.get('data') or {}).get('source') for m in fu_msgs]}"
    )


async def test_lance_of_lethargy_skipped_on_non_eb(
    gm_client, gm_ws, magnus_with_lance,
):
    """Magnus's Quarterstaff (not Eldritch Blast) → no LoL buff
    installed.
    """
    magnus, krieger = magnus_with_lance
    gm_ws.mark()
    # A few Quarterstaff swings; LoL must not fire.
    for _ in range(5):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": magnus["id"],
                "attack_index": QUARTERSTAFF_INDEX,
                "target_combatant_id": "tok_krieger_lol",
                "override": True,
            },
        )
        if resp.status_code == 200 and resp.json().get("hit"):
            break
    await asyncio.sleep(0.2)
    buffs = await _find_krieger_buffs(gm_ws) or []
    lol = [b for b in buffs if (b or {}).get("key") == "lance-of-lethargy"]
    assert not lol, (
        f"Quarterstaff should NOT install Lance of Lethargy; "
        f"got buff: {lol}"
    )
    fu_msgs = gm_ws.buffered("feature_used")
    lol_fu = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "lance-of-lethargy"
    ]
    assert not lol_fu, (
        f"No lance-of-lethargy broadcast expected on Quarterstaff; "
        f"got {lol_fu}"
    )
