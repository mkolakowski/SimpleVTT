"""v2.99.90 — Eldritch Invocation: Repelling Blast.

RAW (PHB p.111): "When you hit a creature with Eldritch Blast, you
can push the creature up to 10 feet away from you in a straight
line."

Server-side ``_apply_repelling_blast_push`` is wired into /attack
right after the hit determination + damage application. When the
attacker has the invocation AND the attack is Eldritch Blast AND
the target was hit AND the target isn't dead, the helper computes
the push vector (target − caster, normalized, scaled to 2 cells),
snaps to grid, commits the new position, and broadcasts
``token_move`` + ``feature_used(source=repelling-blast)``.

v1 makes the push automatic; the optional-decision UI is filed
for follow-up.

Demo fixture: Magnus (Warlock Lv 5) gets the Repelling Blast
invocation added to his feats list in v2.99.90. The harness PATCHes
Krieger to be the target (we know his ID + position), places
both on the active map, and verifies the push fires on a hit.

Tests:
- happy: Magnus + Eldritch Blast + Krieger target → after attack,
  Krieger's token moved 10 ft away from Magnus and the
  feature_used(repelling-blast) broadcast fires.
- gate: Magnus + Quarterstaff (not EB) on Krieger → no push.
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


async def _get_token_xy(gm_client, char_id):
    """Read a character's token position by walking the tokens list."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    for t in r.json()["tokens"]:
        if t.get("character_id") == char_id:
            return float(t["x"]), float(t["y"])
    return None, None


@pytest_asyncio.fixture
async def magnus_and_krieger_placed(gm_client, roster):
    """Place Magnus + Krieger so Krieger is 5 ft east of Magnus
    (one grid cell). After a Repelling Blast push, Krieger should
    be 15 ft east (3 cells). Yields both char dicts.

    Also PATCHes Magnus's feats list to include the Repelling Blast
    invocation so the test runs against any container state (the
    v2.99.90 demo seed edit may or may not have been reseeded into
    the running container).
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    # Ensure Magnus has both Agonizing Blast (for damage
    # consistency) AND Repelling Blast invocations.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"feats": [
            {"slug": "eldritch-invocation-agonizing-blast",
             "name": "Eldritch Invocation: Agonizing Blast"},
            {"slug": "eldritch-invocation-devils-sight",
             "name": "Eldritch Invocation: Devil's Sight"},
            {"slug": "eldritch-invocation-repelling-blast",
             "name": "Eldritch Invocation: Repelling Blast"},
            {"slug": "eldritch-invocation-mask-of-many-faces",
             "name": "Eldritch Invocation: Mask of Many Faces"},
        ]},
    )
    await _place_token(gm_client, magnus["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 420.0, 350.0)
    # Seed Krieger into a battle so target_combatant_id resolution works.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": "tok_magnus_rb", "char_id": magnus["id"],
                 "name": magnus["name"], "initiative": 10,
                 "hp_current": 38, "hp_max": 38, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": "tok_krieger_rb", "char_id": krieger["id"],
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


async def test_repelling_blast_pushes_target_10_ft(
    gm_client, gm_ws, magnus_and_krieger_placed,
):
    """Magnus fires Eldritch Blast at Krieger (1 cell east). After
    a hit, Krieger should be pushed 10 ft east (2 cells) →
    target token's new x is 420 + 2*70 = 560 (cell-snapped).
    """
    magnus, krieger = magnus_and_krieger_placed
    # Long-rest first so Magnus's action chip is fresh.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    # Fire Eldritch Blast at Krieger. Repeat up to 10 times to get
    # a hit (Krieger AC ~16; Magnus EB +6 → roughly 50% hit rate).
    gm_ws.mark()
    krieger_post_x, krieger_post_y = None, None
    hit_seen = False
    for _ in range(15):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": magnus["id"],
                "attack_index": ELDRITCH_BLAST_INDEX,
                "target_combatant_id": "tok_krieger_rb",
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit"):
            hit_seen = True
            await asyncio.sleep(0.15)
            krieger_post_x, krieger_post_y = await _get_token_xy(
                gm_client, krieger["id"],
            )
            break
    assert hit_seen, (
        "Expected at least one EB hit on Krieger across 15 attempts; "
        "extreme statistical anomaly OR auth/setup failed."
    )
    # Krieger should have moved east. The pre-attack x was 420; the
    # post-push x should be 420 + 2*70 = 560 (snapped to cell).
    assert krieger_post_x == 560.0, (
        f"Repelling Blast should push Krieger to x=560 (10 ft east); "
        f"got x={krieger_post_x}"
    )
    assert krieger_post_y == 350.0, (
        f"Repelling Blast should keep Krieger's y at 350 (straight line); "
        f"got y={krieger_post_y}"
    )
    # Verify the feature_used broadcast fired.
    fu_msgs = gm_ws.buffered("feature_used")
    rb = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "repelling-blast"
        and (m.get("data") or {}).get("character_id") == magnus["id"]
    ]
    assert rb, (
        f"Expected feature_used(source=repelling-blast); "
        f"buffered: {[(m.get('data') or {}).get('source') for m in fu_msgs]}"
    )


async def test_repelling_blast_skipped_on_non_eldritch_blast(
    gm_client, gm_ws, magnus_and_krieger_placed,
):
    """Magnus's Quarterstaff (index 0, not Eldritch Blast) on
    Krieger → no push. Krieger stays at his original position.
    """
    magnus, krieger = magnus_and_krieger_placed
    pre_x, pre_y = await _get_token_xy(gm_client, krieger["id"])
    # Fire Quarterstaff at Krieger. The attack might miss; either
    # way the push helper short-circuits on the name gate.
    gm_ws.mark()
    for _ in range(5):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": magnus["id"],
                "attack_index": QUARTERSTAFF_INDEX,
                "target_combatant_id": "tok_krieger_rb",
                "override": True,
            },
        )
        if resp.status_code == 200 and resp.json().get("hit"):
            break
    await asyncio.sleep(0.15)
    post_x, post_y = await _get_token_xy(gm_client, krieger["id"])
    assert post_x == pre_x and post_y == pre_y, (
        f"Quarterstaff should NOT trigger Repelling Blast; "
        f"Krieger moved from ({pre_x},{pre_y}) to ({post_x},{post_y})"
    )
    # No repelling-blast feature_used should fire.
    fu_msgs = gm_ws.buffered("feature_used")
    rb = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "repelling-blast"
    ]
    assert not rb, (
        f"No repelling-blast broadcast expected on Quarterstaff; got {rb}"
    )
